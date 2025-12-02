# Key-Value Store with Leader Replication

## Overview
This project implements a distributed key-value (KV) store featuring single-leader replication. The leader node handles all write operations and replicates data to multiple follower nodes concurrently. Replication uses semi-synchronous approach with configurable quorum for write acknowledgments.

## Architecture
- **Leader Node**: Accepts writes, manages versions, replicates to followers
- **Follower Nodes**: Read-only, receive and apply data updates from leader
- **Replication**: Concurrent writes to all followers with randomized delays to simulate network lag
- **Storage**: In-memory dictionary with atomic operations

## Build and Run
1. Build Docker images:
```bash
docker compose build
```

2. Start services:
```bash
docker compose up -d
```
![alt text](img/image.png)

## Simplified Tests
Run basic tests after starting containers:
```bash
python integration_test.py  # CRUD and concurrency tests
python performance_test.py  # Latency benchmarking with graph
```

## Replication Flow
1. Leader receives write request
2. Stores data locally (increments version)
3. Sends update to all followers concurrently with random delays
4. Waits for quorum acknowledgments
5. Returns success/failure to client

## Performance Analysis
![alt text](img/image%20copy.png)
The system analyzes write latency vs. quorum size. Higher quorum means slower writes due to waiting for more follower acknowledgments. Network delays (50-800 ms) simulate real-world conditions.

A generated chart plots average write latency against different quorum configurations.

## Project Structure
- `app.py`: Main Flask/FastAPI application with replication logic
- `docker-compose.yml`: Multi-container setup
- `Dockerfile`: Application container config
- `tests/`: Integration and performance test scripts
- `README.md`: This documentation

## Dependencies
- FastAPI/Uvicorn for API
- httpx for HTTP client
- matplotlib for plotting
- Python 3.11+, Docker

---