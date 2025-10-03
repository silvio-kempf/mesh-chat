"""
Tests for addressed message functionality.
"""

import pytest
from unittest.mock import Mock

from mesh.protocol import Message, chat
from mesh.node import MeshNode


class TestAddressedMessages:
    """Test addressed message behavior."""

    def setup_nodes(self):
        """Create a three-node mesh for testing."""
        node_a = MeshNode("127.0.0.1", 9001, {("127.0.0.1", 9002), ("127.0.0.1", 9003)}, ttl_default=5)
        node_b = MeshNode("127.0.0.1", 9002, {("127.0.0.1", 9001), ("127.0.0.1", 9003)}, ttl_default=5) 
        node_c = MeshNode("127.0.0.1", 9003, {("127.0.0.1", 9001), ("127.0.0.1", 9002)}, ttl_default=5)
        
        # Mock transports
        for node in [node_a, node_b, node_c]:
            node.transport = Mock()
            
        return node_a, node_b, node_c

    def test_broadcast_displays_everywhere(self):
        """Test that broadcast messages are displayed on all nodes."""
        node_a, node_b, node_c = self.setup_nodes()
        
        # Create broadcast message
        broadcast_msg = chat("127.0.0.1:9001", "hello everyone", ttl=5, dst="")
        
        # Test that all nodes would display it
        assert node_a._should_display(broadcast_msg)
        assert node_b._should_display(broadcast_msg)
        assert node_c._should_display(broadcast_msg)

    def test_addressed_displays_only_target(self):
        """Test that addressed messages display only on target node."""
        node_a, node_b, node_c = self.setup_nodes()
        
        # Create message addressed to node B
        addressed_msg = chat("127.0.0.1:9001", "hello B", ttl=5, dst="127.0.0.1:9002")
        
        # Only B should display it
        assert not node_a._should_display(addressed_msg)
        assert node_b._should_display(addressed_msg)  # Target
        assert not node_c._should_display(addressed_msg)

    def test_addressed_message_to_nonexistent(self):
        """Test handling of messages addressed to non-existent nodes."""
        node_a, node_b, node_c = self.setup_nodes()
        
        # Create message addressed to non-existent node
        nonexistent_msg = chat("127.0.0.1:9001", "orphaned msg", ttl=5, dst="127.0.0.1:9999")
        
        # No node should display it
        assert not node_a._should_display(nonexistent_msg)
        assert not node_b._should_display(nonexistent_msg)
        assert not node_c._should_display(nonexistent_msg)

    def test_addressed_message_forwarding(self):
        """Test that addressed messages are forwarded even if not displayed."""
        node_a, node_b, node_c = self.setup_nodes()
        
        # A sends message addressed to C
        message_from_a_to_c = chat("127.0.0.1:9001", "private to C", ttl=5, dst="127.0.0.1:9003")
        
        # B should forward it even though it doesn't display it
        message_data = message_from_a_to_c.encode()
        node_b.datagram_received(message_data, ("127.0.0.1", 9001))  # A sends to B
        
        # B should have forwarded the message
        assert node_b.transport.sendto.called
        assert node_b.transport.sendto.call_count > 0
        
        # C should forward it too (when it receives it from B)
        node_c.datagram_received(message_data, ("127.0.0.1", 9002))  # B sends to C
        assert node_c.transport.sendto.called

    def test_multiple_addressed_messages_same_target(self):
        """Test multiple addressed messages to the same target."""
        node_a, node_b, node_c = self.setup_nodes()
        
        # Create multiple messages addressed to C
        msg1 = chat("127.0.0.1:9001", "first to C", ttl=5, dst="127.0.0.1:9003")
        msg2 = chat("127.0.0.1:9001", "second to C", ttl=5, dst="127.0.0.1:9003")
        
        # Only C should display both
        assert not node_a._should_display(msg1)
        assert not node_a._should_display(msg2)
        
        assert not node_b._should_display(msg1)
        assert not node_b._should_display(msg2)
        
        assert node_c._should_display(msg1)
        assert node_c._should_display(msg2)

    def test_mixed_broadcast_and_addressed(self):
        """Test handling both broadcast and addressed messages."""
        node_a, node_b, node_c = self.setup_nodes()
        
        broadcast = chat("127.0.0.1:9001", "broadcast", ttl=5, dst="")
        addressed_to_b = chat("127.0.0.1:9001", "to B", ttl=5, dst="127.0.0.1:9002")
        addressed_to_c = chat("127.0.0.1:9001", "to C", ttl=5, dst="127.0.0.1:9003")
        
        # Test B's display logic
        assert node_b._should_display(broadcast)      # Broadcast - yes
        assert node_b._should_display(addressed_to_b) # Addressed to B - yes  
        assert not node_b._should_display(addressed_to_c) # Addressed to C - no
        
        # Test C's display logic
        assert node_c._should_display(broadcast)      # Broadcast - yes
        assert not node_c._should_display(addressed_to_b) # Addressed to B - no
        assert node_c._should_display(addressed_to_c) # Addressed to C - yes


class TestAddressingProtocol:
    """Test addressing syntax and parsing."""

    def test_parse_addressed_message(self):
        """Test parsing @host:port syntax in console input."""
        from mesh.protocol import parse_addressed_message
        
        # Broadcast message (no @)
        msg = parse_addressed_message("hello world", "127.0.0.1:9001", 5)
        assert msg.dst == ""  # Broadcast
        assert msg.body == "hello world"
        
        # Addressed message
        msg = parse_addressed_message("@127.0.0.1:9003 hello world", "127.0.0.1:9001", 5)
        assert msg.dst == "127.0.0.1:9003"
        assert msg.body == "hello world"
        
        # Addressed message with no body
        msg = parse_addressed_message("@127.0.0.1:9003", "127.0.0.1:9001", 5)
        assert msg.dst == "127.0.0.1:9003"
        assert msg.body == ""

    def test_address_formatting(self):
        """Test proper formatting of node addresses."""
        node = MeshNode("127.0.0.1", 9001)
        # Should format as host:port
        assert node._label() == "127.0.0.1:9001"
        
        # Different host/port combinations
        node_hostname = MeshNode("example.com", 8080)
        assert node_hostname._label() == "example.com:8080"
        
        node_different_port = MeshNode("127.0.0.1", 12345)
        assert node_different_port._label() == "127.0.0.1:12345"


class TestMessageKindIntegration:
    """Test interaction between message kinds and addressing."""

    def test_ping_always_broadcast(self):
        """Test that ping messages are always broadcast."""
        from mesh.protocol import ping
        
        # Ping messages should always have dst=""
        ping_msg = ping("127.0.0.1:9001", ttl=4)
        
        # Should be broadcast regardless of TTL
        assert ping_msg.dst == ""
        assert ping_msg.is_broadcast()
        
        # Should not be displayed (they have no body anyway)
        node = MeshNode("127.0.0.1", 9001)
        assert not node._should_display(ping_msg)

    def test_chat_messages_can_be_addressed(self):
        """Test that chat messages can be both broadcast and addressed."""
        from mesh.protocol import chat
        
        # Broadcast chat
        broadcast_chat = chat("127.0.0.1:9001", "hello", ttl=5)
        assert broadcast_chat.dst == ""
        assert broadcast_chat.is_broadcast()
        
        # Addressed chat
        addressed_chat = chat("127.0.0.1:9001", "hello", ttl=5, dst="127.0.0.1:9002")
        assert addressed_chat.dst == "127.0.0.1:9002"
        assert not addressed_chat.is_broadcast()


class TestEdgeCases:
    """Test edge cases for addressed messages."""

    def test_empty_destination_string(self):
        """Test empty destination strings (should be treated as broadcast)."""
        node = MeshNode("127.0.0.1", 9001)
        
        # Messages with dst="" should be broadcast
        broadcast_msg = chat("127.0.0.1:9001", "test", ttl=5, dst="")
        assert node._should_display(broadcast_msg)
        
        # Messages with dst="  " (whitespace) are still addressed
        whitespace_msg = chat("127.0.0.1:9001", "test", ttl=5, dst="   ")
        assert not node._should_display(whitespace_msg)  # Not our address

    def test_self_addressed_messages(self):
        """Test messages addressed to the sender node itself."""
        node_a = MeshNode("127.0.0.1", 9001)
        
        # A sends message to itself
        self_msg = chat("127.0.0.1:9001", "self message", ttl=5, dst="127.0.0.1:9001")
        
        # Should display (addressed to self)
        assert node_a._should_display(self_msg)
        
        # But it's not broadcast
        assert not self_msg.is_broadcast()

    def test_case_sensitivity_in_addresses(self):
        """Test that addresses are case-sensitive."""
        node = MeshNode("127.0.0.1", 9001)
        
        # Case-sensitive comparison
        exact_match = chat("127.0.0.1:9001", "exact", ttl=1, dst="127.0.0.1:9001")
        assert node._should_display(exact_match)
        
        # Case mismatch
        case_mismatch = chat("127.0.0.1:9001", "mismatch", ttl=1, dst="127.0.0.1:9002")
        assert not node._should_display(case_mismatch)
