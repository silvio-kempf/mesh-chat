# Mesh Chat 🌐

A resilient, decentralized chat system where multiple nodes exchange messages using UDP flooding with TTL and de-duplication.

## Why Mesh vs Client-Server?

Traditional client-server architectures have a single point of failure. If the server goes down, all communication stops. A mesh network distributes the communication burden and responsibility across all participants, making the system more resilient to node failures.

## How It Works

Think of it like **gossiping in a neighborhood** - when someone shares news, everyone tells their neighbors, who tell their neighbors, until everyone knows!

### Visual: Your 3 Nodes

```
     Node A                Node B                Node C
  (Port 9001)    <->    (Port 9002)    <->    (Port 9003)
       ▲                                           ▲
       │                                           │
       └───────────────────────────────────────────┘
```

### 📨 Real Example: You Type "hello" in Node A

1. You: "hello" in Node A           ← TTL=8 (8 hops max)
   
2. * Node B receives it             ← TTL=7 (show + forward)
   * Node C receives it             ← TTL=7 (show + forward)
   
3. * Node B forwards to Node C      ← TTL=6 (Node C already has it, so ignore)
   * Node C forwards to Node B      ← TTL=6 (Node B already has it, so ignore)
   
=> All nodes saw "hello" exactly once!
```

### Key Concepts

- **Flooding**: Like a cell phone tower - sends to all friends at once
- **TTL**: "Live 8 hops" - message dies after being forwarded 8 times (no spam!)
- **Deduplication**: "Already heard this news" - drop repeats
- **Addressing**: Private message = write recipient name, Public = everyone sees

### Two Message Types

**Public (Broadcast):**
```bash
hello everyone!          # All nodes see this
```

**Private (Addressed):**
```bash
@127.0.0.1:9003 secret  # Only Node C sees this
```

## Quickstart

### Step 1: Clone & Setup

```bash
# Clone the repository
git clone https://github.com/silvio-kempf/mesh-chat.git
cd mesh-chat

# Verify Python version (3.10+ required)
python --version

# No dependencies needed - uses only standard library!
```

### Step 2: Start the Mesh (3 Terminals)

Open **3 separate terminal windows** and run:

**Terminal 1:**
```bash
cd mesh-chat
python -m mesh.cli --port 9001 --peers 127.0.0.1:9002 127.0.0.1:9003
```

**Terminal 2:**
```bash
cd mesh-chat
python -m mesh.cli --port 9002 --peers 127.0.0.1:9001 127.0.0.1:9003
```

**Terminal 3:**
```bash
cd mesh-chat
python -m mesh.cli --port 9003 --peers 127.0.0.1:9001 127.0.0.1:9002
```

### Step 3: Send Messages

In **any terminal**, type messages and press Enter:

```bash
# Broadcast messages (seen by all nodes)
hello mesh world!
testing UDP flooding

# Private messages (only target sees them)
@127.0.0.1:9003 this is private for node 3
@127.0.0.1:9002 secret message

# Exit cleanly
quit
```

**You'll see:**
- ✅ All nodes receive broadcast messages
- ✅ Private messages only appear on target node
- ✅ TTL decreases with each hop (prevents infinite loops)
- ✅ Duplicate messages are automatically dropped
- ✅ Messages have timestamps and sender labels

## Features

### Implemented
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
