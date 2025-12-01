"""distributed key-value store with single-leader replication"""

import asyncio
import json
import logging
import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Optional

import requests
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Pydantic models for API requests/responses
class WriteRequest(BaseModel):
    key: str
    value: str

class WriteResponse(BaseModel):
    success: bool
    message: str
    quorum_reached: Optional[int] = None

class ReadResponse(BaseModel):
    key: str
    value: Optional[str]
    found: bool

class ReplicationRequest(BaseModel):
    key: str
    value: str
    operation_id: str

class ReplicationResponse(BaseModel):
    success: bool
    operation_id: str

# Environment variables with defaults
NODE_TYPE = os.getenv('NODE_TYPE', 'follower')
LEADER_URL = os.getenv('LEADER_URL', 'http://leader:8000')
WRITE_QUORUM = int(os.getenv('WRITE_QUORUM', '3'))
MIN_DELAY = int(os.getenv('MIN_DELAY', '0'))
MAX_DELAY = int(os.getenv('MAX_DELAY', '1000'))

class KeyValueStore:
    """Simple in-memory key-value store"""

    def __init__(self):
        self.store: Dict[str, str] = {}
        self.lock = threading.Lock()

    def get(self, key: str) -> Optional[str]:
        with self.lock:
            return self.store.get(key)

    def put(self, key: str, value: str) -> None:
        with self.lock:
            self.store[key] = value

    def replicate_data(self, key: str, value: str) -> None:
        """Apply replicated data to store"""
        self.put(key, value)

class ReplicationManager:
    """Handles replication from leader to followers"""

    def __init__(self, store: KeyValueStore):
        self.store = store
        self.follower_urls = [
            'http://follower1:8000',
            'http://follower2:8000',
            'http://follower3:8000',
            'http://follower4:8000',
            'http://follower5:8000'
        ]

    async def replicate_write(self, key: str, value: str, operation_id: str) -> int:
        """Replicate a write to all followers concurrently, return number of confirmations"""
        logger.info(f"Replicating write for key '{key}' with operation_id {operation_id}")

        async def replicate_to_follower(follower_url: str) -> bool:
            """Replicate to a single follower with random delay"""
            # Add random delay to simulate network lag
            if MIN_DELAY > 0 or MAX_DELAY > 0:
                delay_ms = random.randint(MIN_DELAY, MAX_DELAY)
                await asyncio.sleep(delay_ms / 1000.0)
                logger.debug(f"Delay of {delay_ms}ms applied before replicating to {follower_url}")

            try:
                replication_req = ReplicationRequest(
                    key=key,
                    value=value,
                    operation_id=operation_id
                )

                response = requests.post(
                    f"{follower_url}/replicate",
                    json=replication_req.dict(),
                    timeout=5.0
                )

                if response.status_code == 200:
                    resp_data = response.json()
                    if resp_data.get('success'):
                        logger.debug(f"Replication to {follower_url} successful")
                        return True

                logger.error(f"Replication to {follower_url} failed: {response.status_code}")
                return False

            except Exception as e:
                logger.error(f"Exception replicating to {follower_url}: {str(e)}")
                return False

        # Create tasks for concurrent replication to all followers
        tasks = [replicate_to_follower(url) for url in self.follower_urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Count successful replications
        successful_replications = sum(1 for result in results if result is True)
        logger.info(f"Replication complete: {successful_replications}/{len(self.follower_urls)} followers confirmed")

        return successful_replications

class LeaderNode:
    """Represents the leader node that accepts writes and replicates"""

    def __init__(self, store: KeyValueStore):
        self.store = store
        self.replication_manager = ReplicationManager(store)
        self.operation_counter = 0

    def get_operation_id(self) -> str:
        """Generate unique operation ID"""
        with threading.Lock():
            self.operation_counter += 1
            return f"op_{self.operation_counter}"

    async def write(self, key: str, value: str) -> WriteResponse:
        """Handle a write operation with replication"""
        logger.info(f"Leader processing write: key='{key}', value='{value[:50]}...'")

        # Generate operation ID
        operation_id = self.get_operation_id()

        # Write to local store
        self.store.put(key, value)

        # Replicate to followers concurrently
        confirmations = await self.replication_manager.replicate_write(key, value, operation_id)

        # Check if quorum is reached (leader + quorum_offset followers)
        quorum_offset = WRITE_QUORUM - 1  # Leader counts as 1
        quorum_reached = confirmations >= quorum_offset

        if quorum_reached:
            logger.info(f"Write quorum reached: {confirmations}/{quorum_offset} followers confirmed")
            return WriteResponse(
                success=True,
                message="Write successful",
                quorum_reached=confirmations
            )
        else:
            logger.warning(f"Write quorum not reached: {confirmations}/{quorum_offset} followers confirmed")
            return WriteResponse(
                success=False,
                message=f"Write failed: quorum not reached ({confirmations}/{quorum_offset})",
                quorum_reached=confirmations
            )

class FollowerNode:
    """Represents a follower node that is read-only"""

    def __init__(self, store: KeyValueStore):
        self.store = store

    async def read(self, key: str) -> ReadResponse:
        """Handle read operation"""
        value = self.store.get(key)
        return ReadResponse(
            key=key,
            value=value,
            found=value is not None
        )

    async def replicate(self, key: str, value: str, operation_id: str) -> ReplicationResponse:
        """Apply replicated data from leader"""
        logger.info(f"Follower applying replication: key='{key}' for operation {operation_id}")
        self.store.replicate_data(key, value)
        return ReplicationResponse(success=True, operation_id=operation_id)

# Global instances
store = KeyValueStore()

if NODE_TYPE == 'leader':
    node = LeaderNode(store)
else:
    node = FollowerNode(store)

# FastAPI app
app = FastAPI(title="Distributed Key-Value Store", version="1.0.0")

@app.get("/read/{key}")
async def read(key: str):
    """Read a value by key (available on all nodes)"""
    if NODE_TYPE == 'leader':
        # For leader, we need to delegate to FollowerNode for reading
        follower = FollowerNode(store)
        return await follower.read(key)
    else:
        return await node.read(key)

@app.post("/write")
async def write(request: WriteRequest):
    """Write a key-value pair (only available on leader)"""
    if NODE_TYPE != 'leader':
        raise HTTPException(status_code=403, detail="Writes only allowed on leader")

    try:
        response = await node.write(request.key, request.value)
        if not response.success:
            raise HTTPException(status_code=500, detail=response.message)
        return response
    except Exception as e:
        logger.error(f"Error processing write: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.post("/replicate")
async def replicate(request: ReplicationRequest):
    """Internal endpoint for leader to replicate writes to followers"""
    if NODE_TYPE != 'follower':
        raise HTTPException(status_code=403, detail="Replication endpoint only for followers")

    try:
        return await node.replicate(request.key, request.value, request.operation_id)
    except Exception as e:
        logger.error(f"Error processing replication: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy", "node_type": NODE_TYPE}

@app.get("/")
async def root():
    """Root endpoint with service information"""
    return {
        "service": "Distributed Key-Value Store",
        "node_type": NODE_TYPE,
        "endpoints": {
            "read": "GET /read/{key}",
            "write": "POST /write (leader only)",
            "replicate": "POST /replicate (followers only)",
            "health": "GET /health"
        }
    }

if __name__ == "__main__":
    logger.info(f"Starting {NODE_TYPE} node")
    uvicorn.run(app, host="0.0.0.0", port=8000)
