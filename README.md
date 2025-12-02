# Distributed Key-Value Store with Leader-Based Replication

## Overview

This project implements a distributed key-value store using a single-leader replication architecture. The system consists of one leader node and five follower nodes, all running concurrently in Docker containers. The leader handles all write operations and replicates changes to followers with configurable delays that simulate real-world network conditions.

The implementation uses a **semi-synchronous replication** strategy: writes succeed only after receiving acknowledgments from a configurable number of followers (the write quorum). This balances consistency with availability, allowing you to tune the system based on your requirements.

## Architecture
## Project Structure

```
.
├── app.py                           # Main FastAPI application
├── docker-compose.yml                # Cluster configuration
├── Dockerfile                        # Container build instructions
├── requirements.txt                  # Python dependencies
├── img/
│   ├── image.png                    # System overview diagram
│   └── image copy.png               # Latency analysis graph
├── tests/
│   ├── integration_test.py          # CRUD and concurrency tests
│   ├── performance_test.py          # Full latency and consistency analysis
│   └── performance_test_simple.py   # Simplified performance test
├── latency_graph.png                 # Generated performance visualization
└── README.md                         # This file
```

### How It Works

The system follows a straightforward leader-follower pattern:

**Leader Node**
- Accepts all write and delete operations from clients
- Maintains the authoritative version of the data store
- Increments a global version counter with each update
- Replicates changes to all followers concurrently
- Waits for acknowledgments until the quorum threshold is met
- Exposes a FastAPI interface for client operations

**Follower Nodes**
- Read-only from the client's perspective
- Receive replication requests from the leader via `/replicate` endpoint
- Apply updates only if they have a newer version number
- Send acknowledgments back to the leader

### Replication Flow

Here's what happens when you write data:

1. Client sends a write request to the leader
2. Leader applies the write locally and increments the version
3. Leader sends replication requests to all followers concurrently, each with a random delay
4. Followers apply the update and respond with an acknowledgment
5. Leader waits until it receives the required number of acknowledgments (quorum)
6. Leader returns success or failure to the client


The random delays (configurable between 50-800ms) simulate varying network conditions and help demonstrate how quorum size affects write latency.


### Running the System

Start the entire cluster with:

```bash
docker compose build
docker compose up -d
```
![System Overview](img/image.png)

This launches one leader and five followers, all communicating over a private Docker network.

## Implementation Details

### Data Storage and Versioning

The store uses an in-memory dictionary protected by a threading lock:

```python
parameters: Dict[str, Dict[str, any]] = {}
global_version = 0
store_lock = threading.Lock()
```

Every write increments the global version counter:

```python
with store_lock:
    global_version += 1
    parameters[key] = {"value": val, "version": global_version}
```

This versioning ensures that followers can detect and apply only newer updates, preventing stale data from overwriting fresh data.

### Replication with Simulated Network Delays

Each follower receives its replication request with an independent random delay:

```python
def replicate_to_follower(url, k, v, ver, is_del):
    delay_ms = random.uniform(MIN_DELAY, MAX_DELAY)
    time.sleep(delay_ms / 1000)

    payload = {"key": k, "value": v, "version": ver, "delete": is_del}
    response = http_client.post(f"{url}/replicate", json=payload)
    return response.status_code == 200
```

The leader fans out these requests concurrently using a thread pool executor:

```python
tasks = [
    executor.submit(replicate_to_follower, url, k, v, ver, is_del)
    for url in FOLLOWERS
]
```

The quorum logic waits for enough successful acknowledgments:

```python
acks = 0
for future in as_completed(tasks):
    if future.result():
        acks += 1
        if acks >= QUORUM_SIZE:
            return acks
```

### API Endpoints

**Leader: Write Operation**

```python
@app.put("/kv/{key}")
def write_key(key: str, request: WriteRequest):
    if NODE_ROLE != "leader":
        raise HTTPException(403, "Only leader accepts writes")

    # Apply write locally
    with store_lock:
        global_version += 1
        ver = global_version
        parameters[key] = {"value": request.value, "version": ver}

    # Replicate to followers
    acks = perform_replication(key, request.value, ver, delete=False)

    if acks >= QUORUM_SIZE:
        return {"message": "Write successful", "version": ver, "acks": acks}
    
    raise HTTPException(500, f"Quorum not reached ({acks}/{QUORUM_SIZE})")
```

**Follower: Handle Replication**

```python
@app.post("/replicate")
def handle_replication(req: ReplicationRequest):
    if NODE_ROLE != "follower":
        raise HTTPException(403, "This node is not a follower")

    with store_lock:
        existing = parameters.get(req.key)
        
        if req.delete:
            # Delete if version is newer or equal
            if existing is None or req.version >= existing["version"]:
                parameters.pop(req.key, None)
        else:
            # Update if version is newer or equal
            if existing is None or req.version >= existing["version"]:
                parameters[req.key] = {"value": req.value, "version": req.version}

    return {"status": "replicated"}
```

## Testing

### Integration Tests

The integration test suite validates:

- Basic CRUD operations (create, read, update, delete)
- Leader-only write enforcement
- Concurrent write handling
- Replication consistency across followers

Example of concurrent writes:

```python
def writer(i):
    return put_kv(f"concurrent_key_{i % 5}", f"value_{i}")

with ThreadPoolExecutor(max_workers=5) as executor:
    results = list(executor.map(writer, range(10)))
```

### Performance Analysis

The performance test evaluates the system under load by:

- Writing approximately 100 keys
- Using 10 concurrent writers at a time
- Testing across 10 different keys
- Repeating for quorum sizes from 1 to 5

**Metrics Collected:**
- Average latency
- Median latency
- 95th percentile (p95)
- 99th percentile (p99)
- Failure count
- Throughput

After the write storm, the test verifies consistency by reading all keys from the leader and followers, comparing versions to detect any mismatches.

### Performance Results

As expected, higher quorum values increase write latency because the leader must wait for more acknowledgments. Each follower has its own randomized delay, so requiring more acknowledgments means waiting for slower followers.

The generated performance graph clearly shows this relationship between quorum size and latency across different percentiles.

## Consistency Verification

After performance tests complete, the system performs a full consistency check:

```python
for key in all_keys:
    leader_data = read_from_container("leader", key)
    
    for follower in ["f1", "f2", "f3", "f4", "f5"]:
        follower_data = read_from_container(follower, key)
        
        if follower_data["version"] != leader_data["version"]:
            mismatches += 1
            print(f"Mismatch on {key}: {follower} has version {follower_data['version']}, leader has {leader_data['version']}")
```

![Latency Analysis](img/image%20copy.png)

- All followers eventually converge to the leader's state
- Final version numbers match across all nodes
- Small temporary lags during active replication are acceptable
