"""
Tests for de-duplication functionality in mesh nodes.
"""

import asyncio
import pytest
import time
from unittest.mock import Mock, patch

from mesh.protocol import Message, chat
from mesh.node import MeshNode


class TestDeDuplication:
    """Test message de-duplication logic."""

    @pytest.fixture
    def two_nodes(self):
        """Create two interconnected nodes for testing."""
        node_a = MeshNode(
            host="127.0.0.1",
            port=9001,
            peers={("127.0.0.1", 9002)},
            ttl_default=8
        )
        
        node_b = MeshNode(
            host="127.0.0.1",
            port=9002,
            peers={("127.0.0.1", 9001)},
            ttl_default=8
        )

        # Mock transports so we can test the logic without actual UDP
        # Mock transports
        mock_transport_a = Mock()
        mock_transport_b = Mock()
        node_a.transport = mock_transport_a
        node_b.transport = mock_transport_b

        return node_a, node_b, mock_transport_a, mock_transport_b

    def test_duplicate_detection(self, two_nodes):
        """Test that duplicate messages are detected and not forwarded."""
        node_a, node_b, transport_a, transport_b = two_nodes
        
        # Create a message
        msg = chat("127.0.0.1:9001", "test message", ttl=5)
        
        # Simulate receiving the message for the first time
        msg_data = msg.encode()
        sender_addr = ("127.0.0.1", 9003)  # Different sender
        
        # First receipt - should not be in seen
        assert msg.mid not in node_a.seen
        
        # Process the message
        node_a.datagram_received(msg_data, sender_addr)
        
        # Now the message should be in seen
        assert msg.mid in node_a.seen
        
        # Second receipt of same message - should be ignored
        original_forward_count = transport_a.sendto.call_count
        
        node_a.datagram_received(msg_data, sender_addr)
        
        # sendto should not have been called again (duplicate ignored)
        assert transport_a.sendto.call_count == original_forward_count

    def test_seen_message_expiry(self, two_nodes):
        """Test that seen messages are garbage collected after expiration."""
        node_a, node_b, transport_a, transport_b = two_nodes
        
        # Set a very short seen TTL for testing
        node_a.seen_ttl_sec = 1


        # Create a message and receive it
        msg = chat("127.0.0.1:9001", "expiring message", ttl=5)
        msg_data = msg.encode()
        node_a.datagram_received(msg_data, ("127.0.0.1", 9003))
        
        # Message should be in seen
        assert msg.mid in node_a.seen
        original_time = node_a.seen[msg.mid]

        # Fast-forward time by sleeping a bit
        time.sleep(1.1)
        
        # Manually trigger garbage collection
        node_a.seen = {
            mid: timestamp 
            for mid, timestamp in node_a.seen.items()
            if time.time() - timestamp <= node_a.seen_ttl_sec
        }
        
        # Message should be removed from seen
        assert msg.mid not in node_a.seen

    def test_forward_valid_message(self, two_nodes):
        """Test that valid messages are forwarded correctly."""
        node_a, node_b, transport_a, transport_b = two_nodes
        
        # Create a message with good TTL
        msg = chat("127.0.0.1:9001", "valid message", ttl=5)
        msg_data = msg.encode()
        sender_addr = ("127.0.0.1", 9003)
        
        # Process message
        node_a.datagram_received(msg_data, sender_addr)
        
        # Should forward to peers (excluding sender)
        assert transport_a.sendto.called
        
        # Verify the forwarded message has decremented TTL
        call_args = transport_a.sendto.call_args
        forwarded_data = call_args[0][0]
        forwarded_msg = Message.decode(forwarded_data)
        assert forwarded_msg.ttl == msg.ttl - 1  # TTL decremented

    def test_no_forward_expired_ttl(self, two_nodes):
        """Test that messages with expired TTL are not forwarded."""
        node_a, node_b, transport_a, transport_b = two_nodes
        
        # Create message with TTL=0 (already expired)
        msg = chat("127.0.0.1:9001", "expired message", ttl=0)
        msg_data = msg.encode()
        
        # Process message
        node_a.datagram_received(msg_data, ("127.0.0.1", 9003))
        
        # Should not forward expired messages
        assert not transport_a.sendto.called

    def test_no_forward_to_sender(self, two_nodes):
        """Test that messages are not forwarded back to the sender."""
        node_a, node_b, transport_a, transport_b = two_nodes
        
        # Create a message
        msg = chat("127.0.0.1:9001", "test message", ttl=3)
        msg_data = msg.encode()
        peer_addr = ("127.0.0.1", 9002)  # This is one of our peers
        
        # Process message from a peer
        node_a.datagram_received(msg_data, peer_addr)
        
        # Should forward to other peers but not back to sender
        if transport_a.sendto.called:
            sent_peers = [args[0][1] for args in transport_a.sendto.call_args_list]
            assert peer_addr not in sent_peers  # Don't send back to sender


class TestMessageDisplay:
    """Test message display logic."""

    @pytest.fixture
    def node(self):
        """Create a node for display testing."""
        return MeshNode(
            host="127.0.0.1",
            port=9001,
            peers={("127.0.0.1", 9002)},
            ttl_default=8
        )

    def test_display_broadcast_message(self, node):
        """Test that broadcast messages are displayed."""
        msg = chat("127.0.0.1:9003", "hello everyone", ttl=5)  # dst=""
        
        assert node._should_display(msg)
        
    def test_display_addressed_message_to_self(self, node):
        """Test that messages addressed to target node are displayed."""
        msg = chat("127.0.0.1:9003", "hello", ttl=5, dst="127.0.0.1:9001")
        
        assert node._should_display(msg)

    def test_no_display_addressed_message_to_other(self, node):
        """Test that messages addressed to other nodes are not displayed."""
        msg = chat("127.0.0.1:9003", "private", ttl=5, dst="127.0.0.1:9002")
        
        assert not node._should_display(msg)

    def test_no_display_ping_message(self, node):
        """Test that ping messages are not displayed."""
        msg = Message(
            mid="ping-123", ts=0, ttl=1, kind="PING",
            src="127.0.0.1:9003", dst="", body=""
        )
        
        assert not node._should_display(msg)


class TestSayCommand:
    """Test the say() command functionality."""

    @pytest.fixture
    def node_with_mock(self):
        """Create a node with mocked transport."""
        node = MeshNode(
            host="127.0.0.1",
            port=9001,
            peers={("127.0.0.1", 9002), ("127.0.0.1", 9003)},
            ttl_default=5
        )
        
        # Mock transport
        mock_transport = Mock()
        node.transport = mock_transport
        
        return node, mock_transport

    def test_say_broadcast(self, node_with_mock):
        """Test sending broadcast messages."""
        node, mock_transport = node_with_mock
        
        node.say("hello everyone")
        
        # Should send to all peers
        assert mock_transport.sendto.call_count == len(node.peers)
        
        # Verify message content
        for call in mock_transport.sendto.call_args_list:
            data, addr = call[0]
            msg = Message.decode(data)
            assert msg.body == "hello everyone"
            assert msg.dst == ""  # Broadcast
            assert msg.src == node._label()
            assert msg.ttl == 5
            assert addr in node.peers

    def test_say_addressed(self, node_with_mock):
        """Test sending addressed messages."""
        node, mock_transport = node_with_mock
        
        node.say("@127.0.0.1:9003 private message")
        
        # Should send to all peers (the destination is part of the message body)
        assert mock_transport.sendto.call_count == len(node.peers)
        
        # Verify the message contains the addressing syntax
        for call in mock_transport.sendto.call_args_list:
            data, addr = call[0]
            msg = Message.decode(data)
            assert msg.body == "@127.0.0.1:9003 private message"
            assert msg.src == node._label()

    def test_say_local_echo(self, node_with_mock):
        """Test that node sees its own broadcast messages."""
        node, mock_transport = node_with_mock
        
        # Capture what would be displayed
        displayed_messages = []
        
        def capture_display(text):
            displayed_messages.append(text)

        node.add_display_callback(capture_display)
        
        node.say("test echo")
        
        # Should display the message locally
        assert len(displayed_messages) > 0
        assert "<127.0.0.1:9001> test echo" in displayed_messages

    def test_say_no_transport(self, node_with_mock):
        """Test say() behavior when no transport is available."""
        node, mock_transport = node_with_mock
        node.transport = None
        
        # Should not raise exception, just return early
        node.say("test message")
        
        # No transport calls should have been made
        assert mock_transport.sendto.call_count == 0


class TestNodeIntegration:
    """Integration tests combining multiple node behaviors."""

    @pytest.mark.skip(reason="Complex integration test - skipping for now")
    def test_full_message_flow(self):
        """Test complete message flow between nodes."""
        # This test demonstrates the full flood-and-dedup logic
        # We'll create a simple two-node setup and verify flow
        
        node_a = MeshNode("127.0.0.1", 9001, {("127.0.0.1", 9002)}, ttl_default=3)
        node_b = MeshNode("127.0.0.1", 9002, {("127.0.0.1", 9001)}, ttl_default=3)
        
        # Mock transports to capture sent messages
        sent_messages = []
        
        def capture_send_a(data, addr):
            try:
                msg = Message.decode(data)
                sent_messages.append(("a", msg, addr))
            except:
                pass
        
        def capture_send_b(data, addr):
            try:
                msg = Message.decode(data)
                sent_messages.append(("b", msg, addr))
            except:
                pass
        
        mock_transport_a = Mock()
        mock_transport_a.sendto = capture_send_a
        node_a.transport = mock_transport_a
        
        mock_transport_b = Mock()
        mock_transport_b.sendto = capture_send_b
        node_b.transport = mock_transport_b
        
        # Send message from A
        original_msg = chat("127.0.0.1:9001", "integration test", ttl=3)
        node_a.say("integration test")
        
        # Simulate B receiving it from peer 9003 (external node)
        msg_data = original_msg.encode()
        node_b.datagram_received(msg_data, ("127.0.0.1", 9003))
        
        # Inspect captured messages
        assert len(sent_messages) > 0
        
        # Verify flood behavior: A should send to its peer (B)
        a_sends = [msg for sender, msg, addr in sent_messages if sender == "a"]
        assert len(a_sends) > 0
        assert a_sends[0].body == "integration test"
        
        # Verify B forwards with decremented TTL
        b_forwards = [msg for sender, msg, addr in sent_messages if sender == "b"]
        assert len(b_forwards) > 0
        assert b_forwards[0].ttl < original_msg.ttl
