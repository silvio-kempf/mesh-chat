"""
Tests for protocol functionality including encoding/decoding and validation.
"""

import json
import pytest
import uuid
import time

from mesh.protocol import Message, InvalidJSONError, chat, ping, parse_addressed_message


class TestMessage:
    """Test Message dataclass and basic functionality."""

    def test_message_creation(self):
        """Test creating a valid message."""
        msg = Message(
            mid="test-uuid",
            ts=1234.567,
            ttl=8,
            kind="CHAT",
            src="127.0.0.1:9001",
            dst="",
            body="hello world"
        )
        
        assert msg.mid == "test-uuid"
        assert msg.ttl == 8
        assert msg.kind == "CHAT"
        assert msg.src == "127.0.0.1:9001"
        assert msg.dst == ""
        assert msg.body == "hello world"

    def test_is_broadcast(self):
        """Test broadcast detection."""
        broadcast_msg = Message(
            mid="123", ts=0, ttl=1, kind="CHAT", 
            src="127.0.0.1:9001", dst="", body="hello"
        )
        assert broadcast_msg.is_broadcast()

        addressed_msg = Message(
            mid="123", ts=0, ttl=1, kind="CHAT",
            src="127.0.0.1:9001", dst="127.0.0.1:9002", body="hello"
        )
        assert not addressed_msg.is_broadcast()

    def test_is_ping(self):
        """Test ping message detection."""
        ping_msg = Message(
            mid="123", ts=0, ttl=1, kind="PING",
            src="127.0.0.1:9001", dst="", body=""
        )
        assert ping_msg.is_ping()

        chat_msg = Message(
            mid="123", ts=0, ttl=1, kind="CHAT",
            src="127.0.0.1:9001", dst="", body="hello"
        )
        assert not chat_msg.is_ping()

    def test_is_chat(self):
        """Test chat message detection."""
        chat_msg = Message(
            mid="123", ts=0, ttl=1, kind="CHAT",
            src="127.0.0.1:9001", dst="", body="hello"
        )
        assert chat_msg.is_chat()

        ping_msg = Message(
            mid="123", ts=0, ttl=1, kind="PING",
            src="127.0.0.1:9001", dst="", body=""
        )
        assert not ping_msg.is_chat()


class TestMessageEncoding:
    """Test message encoding to bytes."""

    def test_encode_basic_message(self):
        """Test encoding a basic message."""
        msg = Message(
            mid="test-uuid-123",
            ts=1234.567,
            ttl=5,
            kind="CHAT",
            src="127.0.0.1:9001",
            dst="",
            body="hello mesh"
        )
        
        encoded = msg.encode()
        assert isinstance(encoded, bytes)
        
        # Decode back to dict to verify content
        decoded_dict = json.loads(encoded.decode('utf-8'))
        assert decoded_dict["mid"] == "test-uuid-123"
        assert decoded_dict["ts"] == 1234.567
        assert decoded_dict["ttl"] == 5
        assert decoded_dict["kind"] == "CHAT"
        assert decoded_dict["src"] == "127.0.0.1:9001"
        assert decoded_dict["dst"] == ""
        assert decoded_dict["body"] == "hello mesh"

    def test_encode_addressed_message(self):
        """Test encoding an addressed message."""
        msg = Message(
            mid="uuid-456",
            ts=5678.901,
            ttl=3,
            kind="CHAT",
            src="127.0.0.1:9001",
            dst="127.0.0.1:9003",
            body="private message"
        )
        
        encoded = msg.encode()
        decoded_dict = json.loads(encoded.decode('utf-8'))
        assert decoded_dict["dst"] == "127.0.0.1:9003"

    def test_encode_ping_message(self):
        """Test encoding a ping message."""
        msg = Message(
            mid="ping-uuid",
            ts=9999.999,
            ttl=4,
            kind="PING",
            src="127.0.0.1:9001",
            dst="",
            body=""
        )
        
        encoded = msg.encode()
        decoded_dict = json.loads(encoded.decode('utf-8'))
        assert decoded_dict["kind"] == "PING"
        assert decoded_dict["body"] == ""


class TestMessageDecoding:
    """Test message decoding from bytes."""

    def test_decode_valid_message(self):
        """Test decoding a valid message."""
        data = {
            "mid": "test-uuid",
            "ts": 1234.567,
            "ttl": 8,
            "kind": "CHAT",
            "src": "127.0.0.1:9001",
            "dst": "",
            "body": "hello world"
        }
        encoded = json.dumps(data).encode('utf-8')
        
        msg = Message.decode(encoded)
        assert msg.mid == "test-uuid"
        assert msg.ts == 1234.567
        assert msg.ttl == 8
        assert msg.kind == "CHAT"
        assert msg.src == "127.0.0.1:9001"
        assert msg.dst == ""
        assert msg.body == "hello world"

    def test_decode_invalid_json(self):
        """Test decoding invalid JSON."""
        with pytest.raises(InvalidJSONError):
            Message.decode(b"invalid json data")

    def test_decode_missing_fields(self):
        """Test decoding messages missing required fields."""
        incomplete_data = {"mid": "test", "ts": 0}  # Missing other fields
        with pytest.raises(KeyError):
            Message.decode(json.dumps(incomplete_data).encode())

    def test_decode_invalid_field_types(self):
        """Test decoding messages with invalid field types."""
        # Invalid TTL (should be int)
        data = {
            "mid": "test", "ts": 0, "ttl": "not_a_number",
            "kind": "CHAT", "src": "127.0.0.1:9001", "dst": "", "body": ""
        }
        with pytest.raises(ValueError):
            Message.decode(json.dumps(data).encode())

        # Negative TTL
        data = {
            "mid": "test", "ts": 0, "ttl": -1,
            "kind": "CHAT", "src": "127.0.0.1:9001", "dst": "", "body": ""
        }
        with pytest.raises(ValueError):
            Message.decode(json.dumps(data).encode())

        # Invalid message kind
        data = {
            "mid": "test", "ts": 0, "ttl": 5, "kind": "INVALID",
            "src": "127.0.0.1:9001", "dst": "", "body": ""
        }
        with pytest.raises(ValueError):
            Message.decode(json.dumps(data).encode())

    def test_round_trip_encoding(self):
        """Test that encode/decode preserves all fields."""
        original_msg = Message(
            mid="round-trip-uuid",
            ts=12345.678,
            ttl=7,
            kind="CHAT",
            src="192.168.1.100:9001",
            dst="192.168.1.101:9002",
            body="round trip test"
        )
        
        encoded = original_msg.encode()
        decoded_msg = Message.decode(encoded)
        
        assert decoded_msg == original_msg


class TestMessageFactories:
    """Test factory functions for creating messages."""

    def test_chat_factory(self):
        """Test chat message factory."""
        msg = chat(
            src="127.0.0.1:9001",
            body="hello from factory",
            ttl=10,
            dst=""
        )
        
        assert msg.kind == "CHAT"
        assert msg.src == "127.0.0.1:9001"
        assert msg.body == "hello from factory"
        assert msg.ttl == 10
        assert msg.dst == ""
        assert msg.is_broadcast()
        
        # Should generate a UUID
        assert isinstance(msg.mid, str)
        assert len(msg.mid) > 0
        
        # Should have current timestamp
        assert isinstance(msg.ts, (int, float))
        assert msg.ts > 0

    def test_chat_factory_addressed(self):
        """Test chat factory with destination."""
        msg = chat(
            src="127.0.0.1:9001",
            body="private message",
            ttl=5,
            dst="127.0.0.1:9003"
        )
        
        assert not msg.is_broadcast()
        assert msg.dst == "127.0.0.1:9003"

    def test_ping_factory(self):
        """Test ping message factory."""
        msg = ping(src="127.0.0.1:9001", ttl=4)
        
        assert msg.kind == "PING"
        assert msg.src == "127.0.0.1:9001"
        assert msg.ttl == 4
        assert msg.body == ""  # Pings have no body
        assert msg.dst == ""  # Pings are always broadcast
        assert msg.is_broadcast()
        assert msg.is_ping()

    def test_ping_factory_default_ttl(self):
        """Test ping factory with default TTL."""
        msg = ping(src="127.0.0.1:9001")
        assert msg.ttl == 4  # Default ping TTL


class TestAddressedMessageParsing:
    """Test parsing of addressed message syntax."""

    def test_parse_broadcast_message(self):
        """Test parsing a broadcast message."""
        msg = parse_addressed_message("hello world", "127.0.0.1:9001", 8)
        
        assert msg.body == "hello world"
        assert msg.dst == ""  # Broadcast
        assert msg.src == "127.0.0.1:9001"
        assert msg.ttl == 8

    def test_parse_addressed_message(self):
        """Test parsing an addressed message."""
        msg = parse_addressed_message(
            "@127.0.0.1:9003 hello world",
            "127.0.0.1:9001",
            8
        )
        
        assert msg.body == "hello world"
        assert msg.dst == "127.0.0.1:9003"
        assert msg.src == "127.0.0.1:9001"
        assert msg.ttl == 8

    def test_parse_addressed_message_no_body(self):
        """Test parsing addressed message with no body after address."""
        msg = parse_addressed_message("@127.0.0.1:9003", "127.0.0.1:9001", 5)
        
        assert msg.body == ""
        assert msg.dst == "127.0.0.1:9003"

    def test_parse_addressed_message_multiple_spaces(self):
        """Test parsing addressed message with multiple spaces."""
        msg = parse_addressed_message(
            "@127.0.0.1:9003   hello   world",
            "127.0.0.1:9001",
            8
        )
        
        # Should only split on first space
        assert msg.body == "  hello   world"
        assert msg.dst == "127.0.0.1:9003"

    def test_parse_empty_message(self):
        """Test parsing empty message."""
        msg = parse_addressed_message("", "127.0.0.1:9001", 8)
        assert msg.body == ""

    def test_parse_whitespace_only_message(self):
        """Test parsing whitespace-only message."""
        msg = parse_addressed_message("   ", "127.0.0.1:9001", 8)
        # Whitespace is stripped by parse_addressed_message
        assert msg.body == ""


class TestMessageIntegration:
    """Integration tests for message handling."""

    def test_message_comparison(self):
        """Test that messages with same data are equal."""
        msg1 = Message(
            mid="same-id", ts=0, ttl=1, kind="CHAT",
            src="127.0.0.1:9001", dst="", body="test"
        )
        msg2 = Message(
            mid="same-id", ts=0, ttl=1, kind="CHAT",
            src="127.0.0.1:9001", dst="", body="test"
        )
        
        assert msg1 == msg2

    def test_copy_with_modification(self):
        """Test message copy with field modification."""
        original = Message(
            mid="original", ts=0, ttl=5, kind="CHAT",
            src="127.0.0.1:9001", dst="", body="original"
        )
        
        modified = original.copy_with(ttl=3, body="modified")
        
        assert modified.ttl == 3
        assert modified.body == "modified"
        assert modified.mid == "original"  # Unchanged
        assert modified.src == "127.0.0.1:9001"  # Unchanged


def test_unicode_handling():
    """Test that Unicode characters are handled correctly."""
    msg = Message(
        mid="unicode-test",
        ts=1234.567,
        ttl=8,
        kind="CHAT",
        src="127.0.0.1:9001",
        dst="",
        body="Hello 世界! 🚀"
    )
    
    encoded = msg.encode()
    decoded = Message.decode(encoded)
    
    assert decoded.body == "Hello 世界! 🚀"
    assert decoded == msg


def test_edge_case_values():
    """Test edge cases for various fields."""
    # Zero TTL (should be valid)
    msg = chat("127.0.0.1:9001", "zero ttl", ttl=0)
    assert msg.ttl == 0
    
    # Very large TTL
    msg = chat("127.0.0.1:9001", "large ttl", ttl=1000)
    assert msg.ttl == 1000
    
    # Empty body (should be valid)
    msg = chat("127.0.0.1:9001", "", ttl=5)
    assert msg.body == ""
