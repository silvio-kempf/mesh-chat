# Mesh Chat 🌐

A resilient, decentralized chat system where multiple nodes exchange messages using UDP flooding with TTL and de-duplication.

## Why Mesh vs Client-Server?

Traditional client-server architectures have a single point of failure. If the server goes down, all communication stops. A mesh network distributes the communication burden and responsibility across all participants, making the system more resilient to node failures.

## How It Works

```
      192.168.1.100:9001
              │
              ├── 192.168.1.101:9002 ────┐
              │                         │
              └── 192.168.1.102:9003 ───┘
                     │         │
                     └─────────┘
                (Fully Connected Mesh)
```

### Key Concepts

1. **Flooding Algorithm**: When a node receives a message, it forwards to all neighbors except the sender
2. **TTL (Time To Live)**: Each message has a hop limit that decreases with each forward (prevents infinite loops)
3. **De-duplication**: Nodes track seen message IDs to drop duplicate messages
4. **Addressed Messages**: Messages can target specific nodes or broadcast to all

### Message Flow Example
```
Node A sends "hello" → TTL=8
├── Node B receives "hello" → TTL=7 (displays + forwards)
└── Node D receives "hello" → TTL=7 (displays + forwards)
    ├── Node B receives copy (dropped - duplicate)
    └── Node C receives "hello" → TTL=6 (displays + forwards)
```

## Quickstart

### Start Multiple Nodes

Open three terminals and run:

```bash
# Terminal 1
python -m mesh.cli --port 9001 --peers 127.0.0.1:9002 127.0.0.1:9003

# Terminal 2  
python -m mesh.cli --port 9002 --peers 127.0.0.1:9001 127.0.0.1:9003

# Terminal 3
python -m mesh.cli --port 9003 --peers 127.0.0.1:9001 127.0.0.1:9002
```

### Send Messages

In any terminal, type messages and press Enter:

```bash
# Broadcast messages (all nodes see)
hello everyone!
what's up mesh?

# Addressed messages (only target sees)
@127.0.0.1:9003 private message for node 3
@192.168.1.100:9001 hello from across the network
```

## Features ✨

### ✅ Implemented
- **UDP-based Communication**: Each node binds to its own UDP port
- **Message Flooding**: Automatic propagation to all connected peers  
- **De-duplication**: Messages with same ID are dropped (prevents loops)
- **TTL Control**: Configurable hop limits to prevent infinite propagation
- **Addressed Messaging**: Private messages using `@host:port` syntax
- **Cross-platform**: Works on macOS, Linux, Windows
- **Interactive CLI**: Real-time message sending with `--peers` configuration
- **Comprehensive Tests**: 62+ tests covering protocol, nodes, TTL, and addressing

### 🔄 Architecture Components

```
mesh-chat/
├── mesh/
│   ├── protocol.py         # Message encoding/decoding, factories
│   ├── node.py             # MeshNode with UDP relay and deduplication
│   ├── console.py          # Async stdin handler with @ parsing
│   └── cli.py              # Command-line interface
└── tests/
    ├── test_protocol.py    # Message format and validation
    ├── test_node.py        # Flooding and deduplication logic  
    ├── test_ttl.py         # Time-to-live behavior
    └── test_addressed.py   # Private messaging functionality
```

## API Design

### Message Format (JSON)
```json
{
  "mid": "uuid-string",           # Unique message identifier
  "ts": 1730563200.123,          # Unix timestamp
  "ttl": 8,                      # Hops TTL remaining
  "kind": "CHAT",                # Message type: CHAT | PING
  "src": "127.0.0.1:9001",      # Origin node address
  "dst": "",                     # Target ("", or "host:port")
  "body": "hello mesh"           # Message content
}
```

### Node Configuration
```bash
python -m mesh.cli \
  --host 127.0.0.1 \              # Bind address
  --port 9001 \                    # Port number  
  --peers 127.0.0.1:9002 \        # Comma-separated neighbors
  --ttl 8 \                        # Message TTL limit
  --seen-ttl 120                   # Deduplication timeout
```

## Testing & Validation

### Run Tests
```bash
# Full test suite
python -m pytest tests/ -v

# Specific modules
python -m pytest tests/test_protocol.py -v
python -m pytest tests/test_node.py -v
```

### Manual Verification
```bash
# Test 1: Multiple nodes messaging
python -m mesh.cli --port 9001 --peers 127.0.0.1:9002
python -m mesh.cli --port 9002 --peers 127.0.0.1:9001

# Test 2: TTL limiting
python -m mesh.cli --port 9001 --peers 127.0.0.1:9002 --ttl 1

# Test 3: Large mesh
python -m mesh.cli --port 9001 --peers 127.0.0.1:9002 127.0.0.1:9003 127.0.0.1:9004
```

## Implementation Details

### Core Algorithms

1. **De-duplication**: Each node maintains `seen[mid] = timestamp` to track message IDs
2. **Flooding**: Forward to all peers except sender, decrement TTL, record as seen
3. **TTL Handling**: Stop forwarding when TTL ≤ 0
4. **Addressing**: `_should_display()` checks `dst == ""` (broadcast) vs `dst == node_label`

### Network Protocol
- **Transport**: UDP sockets with asyncio.DatagramProtocol
- **Serialization**: Compact JSON with no whitespace
- **Error Handling**: Graceful malformed message dropping
- **Memory Management**: Automatic GC of old message IDs (every 5s)

## Limitations & Trade-offs

### Current Boundaries
- **No Reliability**: UDP packet loss accepted
- **No Persistence**: Messages lost on node restart  
- **No Discovery**: Peers must be manually configured
- **Local Network**: Designed for LAN/intranet use

### Production Considerations
- Add message acknowledgments for reliability
- Implement peer discovery protocols
- Add encryption for security
- Include metrics and monitoring
- Support dynamic topology changes

## Stretch Goals 🚀

### Phase 2 Features
- **End-to-End Encryption**: Public key cryptography per node
- **Peer Discovery**: Automatic neighbor detection via multicast
- **Message Persistence**: Local storage and replay capability  
- **Network Metrics**: Connection health and message statistics
- **File Sharing**: Large message chunking and reassembly

### Advanced Routing
- **Adaptive TTL**: Dynamic hop counts based on network topology
- **Load Balancing**: Intelligent message routing to reduce congestion
- **Fault Tolerance**: Automatic rerouting around failed nodes

## Contributing

1. Fork and clone the repository
2. Run tests: `python -m pytest tests/`
3. Implement features following the existing patterns
4. Add tests and documentation
5. Submit a pull request

## License

MIT License - See LICENSE file for details.
