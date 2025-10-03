"""
Mesh node implementation with UDP communication, flooding, and de-duplication.
"""

import asyncio
import socket
import time
from typing import Dict, Set, Tuple, Optional, Callable

from .protocol import Message, InvalidJSONError


# Type alias for network addresses
Addr = Tuple[str, int]


class MeshNode(asyncio.DatagramProtocol):
    """
    A mesh node that participates in the chat network.
    
    Handles:
    - UDP communication via asyncio.DatagramProtocol
    - Message flooding to neighbors
    - De-duplication of messages
    - TTL decrement and forwarding
    - Addressed message delivery
    """
    
    def __init__(
        self,
        host: str,
        port: int,
        peers: Optional[Set[Addr]] = None,
        ttl_default: int = 8,
        seen_ttl_sec: int = 120
    ):
        """
        Initialize a mesh node.
        
        Args:
            host: Host address to bind to
            port: Port number to bind to
            peers: Set of peer addresses (host, port tuples)
            ttl_default: Default TTL for outgoing messages
            seen_ttl_sec: How long to remember seen message IDs
        """
        super().__init__()
        self.host = host
        self.port = port
        self.addr = (host, port)
        self.peers = peers or set()
        self.ttl_default = ttl_default
        self.seen_ttl_sec = seen_ttl_sec
        
        # Node state
        self.transport: Optional[asyncio.DatagramTransport] = None
        self.seen: Dict[str, float] = {}  # mid -> timestamp first seen
        self.running = False
        
        # Callback for displaying messages
        self.display_callback: Optional[Callable[[str], None]] = None

    def _label(self) -> str:
        """Get the node's network label (host:port)."""
        return f"{self.host}:{self.port}"

    def add_peer(self, peer: Addr) -> None:
        """Add a peer to the node's peer list."""
        self.peers.add(peer)

    def add_display_callback(self, callback: Callable[[str], None]) -> None:
        """Set a callback function for displaying received messages."""
        self.display_callback = callback

    async def start(self) -> None:
        """Start the node by binding to UDP socket and starting background tasks."""
        loop = asyncio.get_running_loop()
        
        # Bind to UDP socket
        try:
            self.transport, _ = await loop.create_datagram_endpoint(
                lambda: self,
                local_addr=self.addr
            )
        except OSError as e:
            raise RuntimeError(f"Failed to bind to {self.addr}: {e}")

        self.running = True
        print(f"Node started on {self._label()}")
        
        if self.peers:
            peer_labels = [f"{host}:{port}" for host, port in self.peers]
            print(f"Connected to peers: {', '.join(peer_labels)}")
        
        # Start background tasks
        asyncio.create_task(self._gc_seen())
        asyncio.create_task(self._heartbeat())

    async def stop(self) -> None:
        """Stop the node and clean up resources."""
        self.running = False
        if self.transport:
            self.transport.close()
        print(f"Node {self._label()} stopped")

    def _should_forward(self, msg: Message, sender_addr: Addr) -> bool:
        """
        Check if a message should be forwarded (not dropped due to duplicates or TTL).
        
        Args:
            msg: The received message
            sender_addr: Address of the sender
            
        Returns:
            True if message should be forwarded
        """
        # Don't forward if we've seen this message before
        if msg.mid in self.seen:
            return False
        
        # Don't forward if TTL has expired
        if msg.ttl <= 0:
            return False
            
        return True

    def _should_display(self, msg: Message) -> bool:
        """
        Check if a message should be displayed on this node.
        
        Args:
            msg: The message to check
            
        Returns:
            True if message should be displayed
        """
        # Always display pings (they have no body anyway)
        if msg.is_ping():
            return False
        
        # For chat messages, check addressing
        if msg.is_broadcast():
            return True  # Broadcast messages are displayed everywhere
        
        # Addressed messages only display on the target node
        return msg.dst == self._label()

    def _forward_message(self, msg: Message, sender_addr: Addr) -> None:
        """
        Forward a message to all peers except the sender.
        
        Args:
            msg: Message to forward
            sender_addr: Address of the original sender
        """
        if not self.transport:
            return

        # Create forwarded message with decremented TTL
        forwarded_msg = msg.copy_with(ttl=msg.ttl - 1)
        forwarded_data = forwarded_msg.encode()

        # Forward to all peers except the sender
        for peer in self.peers:
            if peer != sender_addr:
                try:
                    self.transport.sendto(forwarded_data, peer)
                except Exception as e:
                    print(f"Failed to forward message to {peer}: {e}")

    def _display_message(self, msg: Message) -> None:
        """
        Display a received message.
        
        Args:
            msg: The message to display
        """
        if msg.is_chat():
            display_text = f"<{msg.src}> {msg.body}"
            if self.display_callback:
                self.display_callback(display_text)
            else:
                print(display_text)
        # Pings are not displayed

    # DatagramProtocol interface

    def datagram_received(self, data: bytes, addr: Addr) -> None:
        """
        Handle incoming UDP datagram.
        
        This is called automatically by asyncio when a UDP packet arrives.
        
        Args:
            data: Raw packet data
            addr: [sender's address]
        """
        try:
            # Decode the message
            msg = Message.decode(data)
        except (InvalidJSONError, KeyError, ValueError) as e:
            # Silently ignore malformed messages
            print(f"Failed to decode message from {addr}: {e}")
            return

        # Check if we should process this message
        if not self._should_forward(msg, addr):
            return

        # Record this message as seen
        self.seen[msg.mid] = time.time()

        # Display the message if appropriate
        if self._should_display(msg):
            self._display_message(msg)

        # Forward the message (with decremented TTL)
        self._forward_message(msg, addr)

    def error_received(self, exc: Exception) -> None:
        """Handle UDP transmission errors."""
        print(f"UDP error: {exc}")

    def connection_lost(self, exc: Optional[Exception]) -> None:
        """Called when the UDP transport is closed."""
        if exc:
            print(f"Connection lost: {exc}")
        else:
            print("Connection closed")

    # Message sending methods

    def _send(self, msg: Message, peer: Addr) -> None:
        """
        Send a message to a specific peer.
        
        Args:
            msg: Message to send
            peer: Target peer address
        """
        if not self.transport:
            print("Node not started (no transport)")
            return

        try:
            data = msg.encode()
            self.transport.sendto(data, peer)
        except Exception as e:
            print(f"Failed to send message to {peer}: {e}")

    def say(self, text: str, dst: str = "") -> None:
        """
        Send a chat message.
        
        Args:
            text: Message content
            dst: Destination node label (empty for broadcast)
        """
        if not self.transport:
            print("Node not started")
            return

        # Create the message
        from .protocol import chat
        msg = chat(
            src=self._label(),
            body=text,
            ttl=self.ttl_default,
            dst=dst
        )

        # Display locally first (echo)
        if self._should_display(msg):
            self._display_message(msg)

        # Record as seen to prevent loops
        self.seen[msg.mid] = time.time()

        # Send to all peers
        data = msg.encode()
        for peer in self.peers:
            try:
                self.transport.sendto(data, peer)
            except Exception as e:
                print(f"Failed to send to peer {peer}: {e}")

    def ping_peers(self) -> None:
        """Send ping messages to all peers."""
        if not self.transport or not self.peers:
            return

        from .protocol import ping
        msg = ping(src=self._label(), ttl=4)
        data = msg.encode()
        
        for peer in self.peers:
            try:
                self.transport.sendto(data, peer)
            except Exception as e:
                print(f"Failed to ping peer {peer}: {e}")

    # Background tasks

    async def _gc_seen(self) -> None:
        """Garbage collect old entries from seen messages."""
        while self.running:
            try:
                await asyncio.sleep(5)  # Run every 5 seconds
                
                now = time.time()
                to_remove = []
                
                for mid, first_seen in self.seen.items():
                    if now - first_seen > self.seen_ttl_sec:
                        to_remove.append(mid)
                
                for mid in to_remove:
                    del self.seen[mid]
                
                if to_remove:
                    print(f"Cleaned {len(to_remove)} old message IDs")
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in GC task: {e}")

    async def _heartbeat(self) -> None:
        """Periodically send ping messages to peers."""
        while self.running:
            try:
                await asyncio.sleep(10)  # Ping every 10 seconds
                
                if self.peers:
                    self.ping_peers()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in heartbeat task: {e}")
