"""Custom Key-Value Store with Leader Replication"""

import asyncio
import logging
import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Environment Configuration
NODE_ROLE = os.getenv("ROLE", "follower")  # 'leader' or 'follower'
PORT = int(os.getenv("PORT", 8080))
QUORUM_SIZE = int(os.getenv("WRITE_QUORUM", 3))
MIN_DELAY = float(os.getenv("MIN_DELAY_MS", 50))
MAX_DELAY = float(os.getenv("MAX_DELAY_MS", 1000))

# Followers list from env
FOLLOWERS: List[str] = [
    url.strip() for url in os.getenv("FOLLOWER_URLS", "").split(",") if url.strip()
]

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("kv_app")

# In-memory store - simplified
parameters: Dict[str, Dict[str, any]] = {}
global_version = 0
store_lock = threading.Lock()
replication_executor = ThreadPoolExecutor(max_workers=10)  # Reduced from 20
http_client = httpx.Client(timeout=10)

# Pydantic Models
class WriteRequest(BaseModel):
    value: str

class ReplicationRequest(BaseModel):
    key: str
    value: Optional[str] = None
    version: int
    delete: bool = False

# FastAPI app
app = FastAPI(title="Custom KV Store", description="Leader-based replication KV store")

def replicate_to_follower(follower_url: str, k: str, v: Optional[str], ver: int, is_del: bool) -> bool:
    """Send replication to one follower with random delay"""
    # Simulate network delay
    delay_ms = random.uniform(MIN_DELAY, MAX_DELAY)
    time.sleep(delay_ms / 1000.0)

    payload = {"key": k, "value": v, "version": ver, "delete": is_del}
    try:
        response = http_client.post(f"{follower_url}/replicate", json=payload)
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Replication failed to {follower_url}: {e}")
        return False

def perform_replication(k: str, v: Optional[str], ver: int, is_del: bool) -> int:
    """Replicate update to all followers concurrently and return acks"""
    if not FOLLOWERS:
        return 0

    # Submit replication tasks
    tasks = [
        replication_executor.submit(replicate_to_follower, url, k, v, ver, is_del)
        for url in FOLLOWERS
    ]

    acks_collected = 0
    for future in as_completed(tasks):
        if future.result():
            acks_collected += 1
            # Return early if quorum reached
            if acks_collected >= QUORUM_SIZE:
                return acks_collected

    return acks_collected

@app.get("/kv/{key}")
def read_key(key: str):
    """Read a key-value pair"""
    with store_lock:
        entry = parameters.get(key)

    if entry is None:
        raise HTTPException(status_code=404, detail="Key does not exist")

    return {
        "key": key,
        "value": entry["value"],
        "version": entry["version"]
    }

@app.put("/kv/{key}")
def write_key(key: str, request: WriteRequest):
    """Write/update a key-value pair - Leader only"""
    if NODE_ROLE != "leader":
        raise HTTPException(status_code=403, detail="Write operations allowed on leader only")

    val = request.value
    global global_version

    # Store locally first
    with store_lock:
        global_version += 1
        current_version = global_version
        parameters[key] = {"value": val, "version": current_version}

    # Replicate to followers
    acks_received = perform_replication(key, val, current_version, delete=False)

    if acks_received >= QUORUM_SIZE:
        return {
            "message": "Write successful",
            "key": key,
            "value": val,
            "version": current_version,
            "acks": acks_received
        }
    else:
        # In real implementation, should handle rollback, but for simplicity, fail
        raise HTTPException(
            status_code=500,
            detail=f"Replication quorum not reached ({acks_received}/{QUORUM_SIZE})"
        )

@app.delete("/kv/{key}")
def remove_key(key: str):
    """Delete a key - Leader only"""
    if NODE_ROLE != "leader":
        raise HTTPException(status_code=403, detail="Delete operations allowed on leader only")

    with store_lock:
        if key not in parameters:
            raise HTTPException(status_code=404, detail="Key does not exist")

        global_version += 1
        current_version = global_version
        del parameters[key]

    # Replicate delete
    acks_received = perform_replication(key, None, current_version, delete=True)

    if acks_received >= QUORUM_SIZE:
        return {
            "message": "Delete successful",
            "key": key,
            "version": current_version,
            "acks": acks_received
        }
    else:
        raise HTTPException(
            status_code=500,
            detail=f"Replication quorum not reached ({acks_received}/{QUORUM_SIZE})"
        )

@app.post("/replicate")
def handle_replication(req: ReplicationRequest):
    """Handle replication from leader - Followers only"""
    if NODE_ROLE != "follower":
        raise HTTPException(status_code=403, detail="Replication endpoint for followers only")

    k, v, ver, is_del = req.key, req.value, req.version, req.delete

    with store_lock:
        existing = parameters.get(k)

        if is_del:
            # Only delete if no existing or version is newer
            if existing is None or ver >= existing["version"]:
                parameters.pop(k, None)
        else:
            # Update if no existing or version is newer
            if existing is None or ver >= existing["version"]:
                parameters[k] = {"value": v, "version": ver}

    return {"status": "replicated"}

@app.get("/status")
def get_status():
    """Health check"""
    return {
        "node_type": NODE_ROLE,
        "storage_size": len(parameters),
        "quorum": QUORUM_SIZE,
        "followers": FOLLOWERS
    }

if __name__ == "__main__":
    logger.info(f"Starting {NODE_ROLE} node on port {PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
