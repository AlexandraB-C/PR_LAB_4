# Distributed Key-Value Store with Single-Leader Replication

This project implements a distributed key-value store with single-leader replication using Python, FastAPI, and Docker. The system features leader-based replication where only the leader accepts writes, which are then replicated to follower nodes using semi-synchronous replication with configurable write quorum.

## Architecture

- **Single Leader**: One node accepts writes and coordinates replication
- **Multiple Followers**: Read-only replicas that receive data from the leader
- **Semi-Synchronous Replication**: Writes are acknowledged after quorum confirmation
- **Concurrent Processing**: All nodes handle requests concurrently using asyncio
- **Docker Deployment**: Containerized deployment with docker-compose

## Features

- RESTful API with JSON communication
- Configurable write quorum (1-5 confirmations)
- Random replication delays to simulate network lag
- Data consistency verification across replicas
- Comprehensive error handling and logging
- Health checks and monitoring endpoints

## Project Structure

```
├── app.py              # Main application code
├── requirements.txt    # Python dependencies
├── Dockerfile         # Container definition
├── docker-compose.yml # Multi-node deployment configuration
├── integration_test.py # System integration tests
├── performance_analysis.py # Performance benchmarking
├── README.md          # This documentation
└── requirments.txt    # Original requirements (legacy)
```

## Installation and Setup

### Prerequisites

- Docker and Docker Compose
- Python 3.11+ (for local development)
- curl (for testing)

### Quick Start

1. Clone or download the project files

2. Build and start the distributed system:
```bash
docker-compose up -d --build
```

3. Wait for services to be healthy (check with health endpoints):
```bash
curl http://localhost:8000/health
curl http://localhost:8001/health
```

4. Test basic functionality:
```bash
# Write a key-value pair to leader
curl -X POST http://localhost:8000/write \
  -H "Content-Type: application/json" \
  -d '{"key": "hello", "value": "world"}'

# Read from any node
curl http://localhost:8000/read/hello
curl http://localhost:8001/read/hello
```

## API Endpoints

### Write Endpoint (Leader Only)
- **URL**: `POST /write`
- **Body**: `{"key": "string", "value": "string"}`
- **Response**: `{"success": true, "message": "Write successful", "quorum_reached": 3}`

### Read Endpoint (All Nodes)
- **URL**: `GET /read/{key}`
- **Response**: `{"key": "string", "value": "string", "found": true}`

### Health Check
- **URL**: `GET /health`
- **Response**: `{"status": "healthy", "node_type": "leader|follower"}`

### Service Info
- **URL**: `GET /`
- **Response**: Service information and endpoint list

### Replication Endpoint (Internal)
- **URL**: `POST /replicate` (followers only)
- **Body**: `{"key": "string", "value": "string", "operation_id": "string"}`

## Configuration

All configuration is done through environment variables in `docker-compose.yml`.

### Node Configuration
- `NODE_TYPE`: `leader` or `follower`
- `LEADER_URL`: URL of the leader (for followers, default: http://leader:8000)

### Replication Configuration
- `WRITE_QUORUM`: Number of confirmations needed (1-5, leader only, default: 3)
- `MIN_DELAY`: Minimum replication delay in ms (default: 0)
- `MAX_DELAY`: Maximum replication delay in ms (default: 1000)

## Testing and Verification

### Setup Verification

First, verify your system has all required tools:

```bash
python3 verify_setup.py
# or
make check
```

This checks:
- Docker and Docker Compose installation
- Python packages and dependencies
- Port availability (8000-8005)
- Docker daemon status
- Internet connectivity

### Quick Test (under 2 minutes)

Run a fast verification of basic functionality:

```bash
./quick_test.sh
# or
make quick
```

This script:
- Builds and starts all services
- Waits for health checks
- Performs basic write/read operations via curl
- Verifies responses and consistency
- Cleans up automatically

### Basic Test (under 2 minutes)

Simple Python test with detailed output:

```bash
python3 test_basic.py
# or
make basic
```

Features:
- 5-10 write operations
- Reads from all 6 nodes
- Clear consistency verification
- Automatic cleanup

### Full Integration Tests

Comprehensive test suite:

```bash
python3 integration_test.py
# or
make test
```

Tests include:
- Basic write operations to leader
- Data consistency across all nodes with detailed error reporting
- Multiple concurrent writes
- Authorization (writes rejected on followers)
- Error handling scenarios

### Performance Analysis

Run comprehensive performance analysis with quorum testing:

```bash
python3 performance_analysis.py
# or
make perf
```

This will:
- Test quorums from 1 to 5
- Perform ~100 concurrent writes per quorum
- Generate latency and success rate plots
- Verify data consistency after testing

## Design Decisions

### Leader-Based Replication

Following the single-leader model from "Designing Data-Intensive Applications":
- Leader handles all writes and coordinates replication
- Followers are read-only for external clients
- Simplifies conflict resolution and consistency guarantees

### Semi-Synchronous Replication

- Leader writes locally first
- Replicates to all followers concurrently
- Waits for quorum confirmation before acknowledging success
- Balances consistency and availability

### Concurrent Processing

- Uses asyncio for I/O operations
- ThreadPoolExecutor for CPU-bound tasks
- Handles multiple requests simultaneously
- Replication requests are fully concurrent

### Error Handling

- Graceful degradation when nodes become unavailable
- Detailed logging for debugging
- HTTP status codes for API errors
- Timeouts and retries for network operations

## Performance Characteristics

Expected behavior based on quorum settings:

- **Quorum 1**: Lowest latency, highest availability, weakest consistency
- **Quorum 2-3**: Balance of latency and consistency
- **Quorum 4-5**: Highest consistency but slower writes, less fault tolerant

The replication delays (MIN_DELAY/MAX_DELAY) simulate network latency and add variance to operation timing.

## Monitoring and Troubleshooting

### Logs

Check container logs:
```bash
docker-compose logs leader
docker-compose logs follower1
```

### Health Checks

Monitor node health:
```bash
curl http://localhost:8000/health
# Expected: {"status": "healthy", "node_type": "leader"}
```

### Common Issues

1. **Services not starting**: Check Docker resources and ports
2. **Replication failures**: Verify network connectivity between containers
3. **Quorum not reached**: Some follower nodes may be unhealthy
4. **High latency**: Check MIN_DELAY/MAX_DELAY configuration

### Manual Testing

```bash
# Write to leader
curl -X POST http://localhost:8000/write -H "Content-Type: application/json" -d '{"key": "test", "value": "data"}'

# Read from different nodes
curl http://localhost:8000/read/test  # Leader
curl http://localhost:8001/read/test  # Follower 1
curl http://localhost:8002/read/test  # Follower 2

# Try writing to follower (should fail)
curl -X POST http://localhost:8001/write -H "Content-Type: application/json" -d '{"key": "test2", "value": "data"}'
# Expected: 403 Forbidden
```

## Development

### Local Development

Run without Docker for development:

```bash
# Install dependencies
pip install -r requirements.txt

# Run leader
NODE_TYPE=leader python app.py

# Run follower (in another terminal)
NODE_TYPE=follower LEADER_URL=http://localhost:8000 python app.py
```

### Code Structure

- `KeyValueStore`: In-memory storage with thread-safe operations
- `ReplicationManager`: Handles concurrent replication to followers
- `LeaderNode`: Manages write operations and quorum checking
- `FollowerNode`: Handles reads and receives replications
- `FastAPI app`: REST endpoints and request routing

## License

This project is for educational purposes. Feel free to use and modify.

## References

- "Designing Data-Intensive Applications" by Martin Kleppmann
- FastAPI documentation
- Docker Compose documentation
