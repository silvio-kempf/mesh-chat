"""
Console input handling for interactive mesh chat.
Supports both broadcast and addressed messages.
"""

import asyncio
import sys
from typing import Optional

from .node import MeshNode


class MeshConsole:
    """
    Handles interactive console input for mesh chat.
    
    Features:
    - Async stdin reading (non-blocking)
    - Support for @host:port addressing syntax
    - Clean shutdown on Ctrl+C
    """
    
    def __init__(self, node: MeshNode):
        """
        Initialize console with a mesh node.
        
        Args:
            node: The mesh node to send messages through
        """
        self.node = node
        self.running = False

    async def start(self) -> None:
        """Start the interactive console loop."""
        self.running = True
        print(f"Mesh console started. Type messages (or use @host:port for addressing):")
        print("Examples:")
        print("  hello world  -> broadcast to all nodes")
        print("  @127.0.0.1:9003 hello world  -> send only to 127.0.0.1:9003")
        print("  Type 'quit' or 'exit' to stop")
        print()

        # Start the input reader task
        try:
            await self._input_loop()
        except KeyboardInterrupt:
            pass
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Stop the console."""
        self.running = False
        print("\nConsole stopped.")

    async def _input_loop(self) -> None:
        """Main input processing loop."""
        # Use asyncio.to_thread to avoid blocking the event loop
        loop = asyncio.get_running_loop()
        
        while self.running:
            try:
                # Read input in a thread to avoid blocking
                line = await loop.run_in_executor(None, self._read_line)
                
                if not self.running:  # Check if we were asked to stop
                    break
                    
                if line:
                    await self._process_input(line)
                    
            except KeyboardInterrupt:
                print("\nReceived interrupt signal")
                break
            except EOFError:
                print("\nEOF received")
                break
            except Exception as e:
                print(f"Error reading input: {e}")
                break

    def _read_line(self) -> Optional[str]:
        """Read a line from stdin (runs in thread)."""
        try:
            return input().strip()
        except (EOFError, KeyboardInterrupt):
            return None

    async def _process_input(self, line: str) -> None:
        """
        Process user input and send appropriate messages.
        
        Args:
            line: The input line from the user
        """
        line = line.strip()
        
        # Handle restart commands
        if line.lower() in ('quit', 'exit', 'q'):
            self.running = False
            return
        
        # Handle empty input
        if not line:
            return

        # Parse addressed syntax and send the message
        try:
            from .protocol import parse_addressed_message
            import time
            
            msg = parse_addressed_message(line, self.node._label(), self.node.ttl_default)
            
            # Send the parsed message directly to peers
            if self.node.transport:
                # Record as seen to prevent loops from our own message
                self.node.seen[msg.mid] = time.time()
                
                # Display locally first (echo)
                if self.node._should_display(msg):
                    self.node._display_message(msg)
                    
                # Send to all peers  
                msg_data = msg.encode()
                for peer in self.node.peers:
                    try:
                        self.node.transport.sendto(msg_data, peer)
                    except Exception as e:
                        print(f"Failed to send to peer {peer}: {e}")
            else:
                print("Node not started")
        except Exception as e:
            print(f"Failed to send message: {e}")


class AsyncConsoleReader:
    """
    Alternative console reader using asyncio streams.
    This might be more appropriate for some environments.
    """
    
    def __init__(self, node: MeshNode):
        self.node = node
        self.running = False

    async def start(self) -> None:
        """Start reading from stdin asynchronously."""
        self.running = True
        
        print("Mesh console started. Type messages:")
        print("Examples:")
        print("  hello world  -> broadcast")
        print("  @127.0.0.1:9003 hello world  -> addressed")
        print("  Type 'quit' to exit")
        print()

        try:
            # Create stdin stream reader
            reader = asyncio.StreamReader()
            protocol = asyncio.StreamReaderProtocol(reader)
            transport, _ = await asyncio.get_running_loop().connect_read_pipe(
                lambda: protocol, sys.stdin
            )

            # Process input lines
            while self.running:
                try:
                    line_bytes = await asyncio.wait_for(reader.readline(), timeout=0.1)
                    line = line_bytes.decode().strip()
                    
                    if not self.running:
                        break
                        
                    if line:
                        await self._process_input(line)
                        
                except asyncio.TimeoutError:
                    continue  # Check running status periodically
                except Exception as e:
                    print(f"Error processing input: {e}")
                    break

            transport.close()

        except KeyboardInterrupt:
            pass
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Stop the console reader."""
        self.running = False

    async def _process_input(self, line: str) -> None:
        """Process user input."""
        line = line.strip()
        
        if line.lower() in ('quit', 'exit', 'q'):
            self.running = False
            return
            
        if not line:
            return

        try:
            from .protocol import parse_addressed_message
            import time
            
            msg = parse_addressed_message(line, self.node._label(), self.node.ttl_default)
            
            if self.node.transport:
                self.node.seen[msg.mid] = time.time()
                
                if self.node._should_display(msg):
                    self.node._display_message(msg)
                    
                msg_data = msg.encode()
                for peer in self.node.peers:
                    try:
                        self.node.transport.sendto(msg_data, peer)
                    except Exception as e:
                        print(f"Failed to send to peer {peer}: {e}")
            else:
                print("Node not started")
        except Exception as e:
            print(f"Failed to send message: {e}")


# Convenience function for easy console integration

async def start_console(node: MeshNode, use_streams: bool = False) -> None:
    """
    Start an interactive console with the given mesh node.
    
    Args:
        node: Mesh node to send messages through
        use_streams: If True, use AsyncConsoleReader (streams). 
                    If False, use MeshConsole (threading).
    """
    if use_streams:
        console = AsyncConsoleReader(node)
        await console.start()
    else:
        console = MeshConsole(node)
        await console.start()

