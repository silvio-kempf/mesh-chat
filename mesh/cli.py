"""
Command-line interface for mesh chat nodes.
Handles argument parsing and node startup.
"""

import argparse
import asyncio
import signal
import sys
from typing import List, Set, Tuple

# Try to use uvloop on Linux for better performance
try:
    import uvloop
    if sys.platform != 'win32':
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
    pass

from .node import MeshNode, Addr
from .console import start_console


def parse_peer_address(peer_str: str) -> Addr:
    """
    Parse a peer address string into (host, port) tuple.
    
    Args:
        peer_str: Address string like "127.0.0.1:9002"
        
    Returns:
        Tuple of (host, port)
        
    Raises:
        ValueError: If address format is invalid
    """
    try:
        host, port_str = peer_str.rsplit(':', 1)
        port = int(port_str)
        
        if not 1 <= port <= 65535:
            raise ValueError(f"Port must be between 1 and 65535, got {port}")
            
        return (host, port)
        
    except ValueError as e:
        if ':' not in peer_str:
            raise ValueError(f"Peer address must be in format 'host:port', got '{peer_str}'")
        raise ValueError(f"Invalid peer address '{peer_str}': {e}")


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Start a mesh chat node",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start three nodes as peers
  python -m mesh.cli --port 9001 --peers 127.0.0.1:9002 127.0.0.1:9003
  python -m mesh.cli --port 9002 --peers 127.0.0.1:9001 127.0.0.1:9003  
  python -m mesh.cli --port 9003 --peers 127.0.0.1:9001 127.0.0.1:9002

  # Use different host and TTL
  python -m mesh.cli --host 0.0.0.0 --port 9001 --peers 192.168.1.2:9002 --ttl 16

Message syntax:
  hello world  -> broadcast message to all peers
  @127.0.0.1:9003 hello world  -> addressed message to specific peer
        """
    )

    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host address to bind to (default: 127.0.0.1)"
    )

    parser.add_argument(
        "--port",
        type=int,
        required=True,
        help="Port number to bind to (required)"
    )

    parser.add_argument(
        "--peers",
        nargs="*",
        default=[],
        help="List of peer addresses in format host:port"
    )

    parser.add_argument(
        "--ttl",
        type=int,
        default=8,
        help="Default TTL (time-to-live) for messages (default: 8)"
    )

    parser.add_argument(
        "--seen-ttl",
        type=int,
        default=120,
        help="How long to remember seen message IDs in seconds (default: 120)"
    )

    parser.add_argument(
        "--use-streams",
        action="store_true",
        help="Use async streams for console input (alternative implementation)"
    )

    parser.add_argument(
        "--version",
        action="version",
        version="mesh-chat 0.1.0"
    )

    args = parser.parse_args()

    # Validate arguments
    if not 1 <= args.port <= 65535:
        parser.error(f"Port must be between 1 and 65535, got {args.port}")

    if args.ttl < 1:
        parser.error(f"TTL must be at least 1, got {args.ttl}")

    if args.seen_ttl < 1:
        parser.error(f"Seen TTL must be at least 1, got {args.seen_ttl}")
    
    # Check if trying to add self as peer
    peer_addresses = set()
    for peer_str in args.peers:
        try:
            peer_addr = parse_peer_address(peer_str)
            peer_addresses.add(peer_addr)
            
            # Ensure we don't add ourselves as a peer
            if peer_addr == (args.host, args.port):
                parser.error(f"Cannot add self ({peer_str}) as a peer")
                
        except ValueError as e:
            parser.error(str(e))

    args.peers = peer_addresses
    return args


class MeshNodeRunner:
    """Manages the lifecycle of a mesh node and handles shutdown."""
    
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.node: MeshNode = None
        self.shutdown_event = asyncio.Event()

    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        if sys.platform != 'win32':
            # On Unix systems, handle SIGINT and SIGTERM
            loop = asyncio.get_running_loop()
            loop.add_signal_handler(signal.SIGINT, self._signal_handler)
            loop.add_signal_handler(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self) -> None:
        """Handle shutdown signals."""
        print("\nReceived shutdown signal...")
        self.shutdown_event.set()

    async def run(self) -> None:
        """Run the mesh node."""
        try:
            # Create and configure the node
            self.node = MeshNode(
                host=self.args.host,
                port=self.args.port,
                peers=self.args.peers,
                ttl_default=self.args.ttl,
                seen_ttl_sec=self.args.seen_ttl
            )

            # Setup signal handlers
            self._setup_signal_handlers()

            # Start the node
            await self.node.start()

            # Start console input handling
            console_task = asyncio.create_task(
                start_console(self.node, use_streams=self.args.use_streams)
            )

            # Wait for shutdown signal
            try:
                await asyncio.wait_for(
                    self.shutdown_event.wait(),
                    timeout=None
                )
            except KeyboardInterrupt:
                pass  # Already handled by signal handler

            print("\nShutting down...")

            # Cancel console task
            console_task.cancel()
            try:
                await console_task
            except asyncio.CancelledError:
                pass

            # Stop the node
            await self.node.stop()

        except Exception as e:
            print(f"Error running mesh node: {e}")
            raise


async def main() -> None:
    """Main entry point."""
    try:
        args = parse_arguments()
        runner = MeshNodeRunner(args)
        await runner.run()
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

