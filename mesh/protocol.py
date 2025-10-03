"""
Message protocol for mesh chat communication.
Handles encoding/decoding and message validation.
"""

import json
import time
import uuid
from dataclasses import dataclass, replace
from typing import Dict, Any, Optional


@dataclass(frozen=True)
class Message:
    """
    A message in the mesh network.
    
    Fields:
        mid: Unique message identifier (UUID string)
        ts: Unix timestamp when message was created
        ttl: Time-to-live (hops remaining)
        kind: Message type ("CHAT" or "PING")
        src: Source node label (host:port)
        dst: Destination node label (empty for broadcast)
        body: Message content
    """
    mid: str
    ts: float
    ttl: int
    kind: str
    src: str
    dst: str
    body: str

    def encode(self) -> bytes:
        """Encode message to JSON bytes for UDP transmission."""
        data = {
            "mid": self.mid,
            "ts": self.ts,
            "ttl": self.ttl,
            "kind": self.kind,
            "src": self.src,
            "dst": self.dst,
            "body": self.body
        }
        return json.dumps(data, separators=(',', ':')).encode('utf-8')

    @staticmethod
    def decode(buf: bytes) -> 'Message':
        """
        Decode JSON bytes to Message object.
        
 against:
            InvalidJSONError: If buffer contains invalid JSON
            KeyError: If required fields are missing
            ValueError: If field values are invalid
        """
        try:
            data = json.loads(buf.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise InvalidJSONError(f"Failed to decode JSON: {e}")

        # Validate required fields
        required_fields = ["mid", "ts", "ttl", "kind", "src", "dst", "body"]
        for field in required_fields:
            if field not in data:
                raise KeyError(f"Missing required field: {field}")

        # Validate field types and values
        if not isinstance(data["mid"], str) or not data["mid"]:
            raise ValueError("mid must be a non-empty string")
        
        if not isinstance(data["ts"], (int, float)) or data["ts"] < 0:
            raise ValueError("ts must be a non-negative number")
        
        if not isinstance(data["ttl"], int) or data["ttl"] < 0:
            raise ValueError("ttl must be a non-negative integer")
        
        if data["kind"] not in ["CHAT", "PING"]:
            raise ValueError("kind must be 'CHAT' or 'PING'")
        
        if not isinstance(data["src"], str) or not data["src"]:
            raise ValueError("src must be a non-empty string")
        
        if not isinstance(data["dst"], str):
            raise ValueError("dst must be a string")
        
        if not isinstance(data["body"], str):
            raise ValueError("body must be a string")

        return Message(
            mid=data["mid"],
            ts=data["ts"],
            ttl=data["ttl"],
            kind=data["kind"],
            src=data["src"],
            dst=data["dst"],
            body=data["body"]
        )

    def copy_with(self, **kwargs) -> 'Message':
        """Create a new message with some fields updated."""
        return replace(self, **kwargs)

    def is_broadcast(self) -> bool:
        """Check if this is a broadcast message (no specific destination)."""
        return self.dst == ""

    def is_ping(self) -> bool:
        """Check if this is a ping message."""
        return self.kind == "PING"

    def is_chat(self) -> bool:
        """Check if this is a chat message."""
        return self.kind == "CHAT"


class InvalidJSONError(Exception):
    """Raised when JSON decoding fails."""
    pass


# Factory functions for creating common message types

def chat(src: str, body: str, ttl: int, dst: str = "") -> Message:
    """
    Create a chat message.
    
    Args:
        src: Source node label (host:port)
        body: Message content
        ttl: Time-to-live (hops)
        dst: Destination node label (empty for broadcast)
    
    Returns:
        Message object ready for transmission
    """
    return Message(
        mid=str(uuid.uuid4()),
        ts=time.time(),
        ttl=ttl,
        kind="CHAT",
        src=src,
        dst=dst,
        body=body
    )


def ping(src: str, ttl: int = 4) -> Message:
    """
    Create a ping message for heartbeat/liveness.
    
    Args:
        src: Source node label (host:port)
        ttl: Time-to-live (hops, default 4)
    
    Returns:
        Ping message object
    """
    return Message(
        mid=str(uuid.uuid4()),
        ts=time.time(),
        ttl=ttl,
        kind="PING",
        src=src,
        dst="",  # Pings are always broadcast
        body=""  # Ping messages have no body
    )


def parse_addressed_message(text: str, src: str, ttl: int) -> Message:
    """
    Parse user input that might contain addressing syntax.
    
    Args:
        text: User input text (may start with @host:port)
        src: Source node label (host:port)
        ttl: Default TTL for the message
    
    Returns:
        Message object with appropriate dst field
    
    Examples:
        "hello world" -> broadcast message
        "@127.0.0.1:9003 hello world" -> addressed message to 127.0.0.1:9003
    """
    text = text.strip()  # Strip only leading/trailing whitespace
    
    if text.startswith("@"):
        # Parse addressed message: @host:port message body
        parts = text[1:].split(" ", 1)  # Split on first space only
        if len(parts) < 2:
            dst, body = parts[0], ""
        else:
            dst, body = parts[0], parts[1]
        
        return chat(src, body, ttl, dst)
    else:
        # Broadcast message
        return chat(src, text, ttl)
