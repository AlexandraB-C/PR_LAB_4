# Simple Integration Tests for My Custom KV Store
import json
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError
from urllib.request import Request, urlopen

LEADER_URL = "http://localhost:8000"

def wait_for_leader():
    print("Waiting for leader...")
    for _ in range(30):
        try:
            with urlopen(f"{LEADER_URL}/status", timeout=1) as resp:
                data = json.loads(resp.read().decode())
                if data.get("node_type") == "leader":
                    print(" Leader ready!")
                    return True
        except:
            pass
        time.sleep(1)
    print("Leader not ready.")
    return False

def put_kv(k, v):
    url = f"{LEADER_URL}/kv/{k}"
    data = json.dumps({"value": v}).encode()
    req = Request(url, data=data, headers={"Content-Type": "application/json"}, method="PUT")
    try:
        with urlopen(req, timeout=5) as r:
            return json.loads(r.read().decode())
    except HTTPError:
        return None

def get_kv(k):
    try:
        with urlopen(f"{LEADER_URL}/kv/{k}", timeout=5) as r:
            return json.loads(r.read().decode())
    except HTTPError as e:
        if e.code == 404:
            return None
        return None

def del_kv(k):
    req = Request(f"{LEADER_URL}/kv/{k}", method="DELETE")
    try:
        with urlopen(req, timeout=5) as r:
            return json.loads(r.read().decode())
    except HTTPError:
        return None

def test_crud():
    print("\n--- CRUD Operations Test ---")
    k = "test_key"
    v = "test_value"
    # Write
    res = put_kv(k, v)
    assert res and "version" in res
    print(f" Write success: {res['message']}")
    # Read
    data = get_kv(k)
    assert data and data["value"] == v
    print(f" Read success: {data['value']}")
    # Delete
    del_res = del_kv(k)
    assert del_res and "version" in del_res
    print(f" Delete success: {del_res['message']}")
    # Read after delete
    assert get_kv(k) is None
    print(" Read after delete: 404 OK")

def test_concurrency():
    print("\n--- Concurrency Test ---")
    k = "race_key"
    writes = 10
    def writer(i):
        return put_kv(k, f"val_{i}")

    with ThreadPoolExecutor(max_workers=5) as ex:
        results = list(ex.map(writer, range(writes)))

    success_count = sum(1 for r in results if r)
    # Due to concurrency, some may fail, but at least one should succeed
    final = get_kv(k)
    if final:
        print(f" Final value: {final['value']}, version: {final['version']}")
    else:
        print(" No value after concurrency test")

def main():
    if not wait_for_leader():
        return
    try:
        test_crud()
        test_concurrency()
        print("\nBasic tests PASSED")
    except AssertionError as e:
        print(f"Test failed: {e}")

if __name__ == "__main__":
    main()
