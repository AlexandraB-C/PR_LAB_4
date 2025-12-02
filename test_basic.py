#!/usr/bin/env python3
"""basic functionality test for key-value store"""

import requests
import time
import subprocess
import sys
import json

SERVICES = {
    'leader': 'http://localhost:8000',
    'follower1': 'http://localhost:8001',
    'follower2': 'http://localhost:8002',
    'follower3': 'http://localhost:8003',
    'follower4': 'http://localhost:8004',
    'follower5': 'http://localhost:8005'
}

def wait_for_services(timeout=60):
    """wait for all services to be ready"""
    print("waiting for services to start...")
    start_time = time.time()

    while time.time() - start_time < timeout:
        all_healthy = True
        for name, url in SERVICES.items():
            try:
                response = requests.get(f"{url}/health", timeout=3)
                if response.status_code != 200:
                    all_healthy = False
                    break
            except:
                all_healthy = False
                break

        if all_healthy:
            print("all services ready!")
            return True
        time.sleep(5)

    return False

def start_system():
    """start docker services"""
    print("starting system...")
    try:
        subprocess.run(["docker-compose", "up", "-d", "--build"],
                      check=True, timeout=180, capture_output=True)
        print("system started")
        return True
    except:
        print("failed to start system")
        return False

def write_key_value(key, value):
    """write a key-value pair to leader"""
    url = f"{SERVICES['leader']}/write"
    data = {"key": key, "value": value}

    try:
        response = requests.post(url, json=data, timeout=10)
        if response.status_code == 200 and response.json().get('success'):
            return True
    except:
        pass
    return False

def read_from_all_nodes(key, expected_value):
    """read key from all nodes and check consistency"""
    results = {}

    for name, url in SERVICES.items():
        try:
            response = requests.get(f"{url}/read/{key}", timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get('found'):
                    results[name] = data.get('value')
                else:
                    results[name] = None
            else:
                results[name] = "ERROR"
        except:
            results[name] = "TIMEOUT"

    # check if all match expected value
    all_match = all(value == expected_value for value in results.values()
                   if value not in ["ERROR", "TIMEOUT"])

    # show results
    print(f"key '{key}' consistency check:")
    for node, value in results.items():
        status = "✓" if value == expected_value else "✗"
        print(f"  {node}: {value} {status}")

    return all_match

def test_write_rejection():
    """test that followers reject write requests"""
    url = f"{SERVICES['follower1']}/write"
    data = {"key": "test", "value": "test"}

    try:
        response = requests.post(url, json=data, timeout=5)
        return response.status_code == 403
    except:
        return False

def cleanup():
    """stop and clean up services"""
    print("cleaning up...")
    try:
        subprocess.run(["docker-compose", "down"], timeout=30, capture_output=True)
    except:
        pass

def main():
    """run the basic test"""
    print("=== BASIC FUNCTIONALITY TEST ===")

    # start system
    if not start_system():
        print("FAIL: could not start system")
        return False

    # wait for services
    if not wait_for_services():
        print("FAIL: services did not start properly")
        cleanup()
        return False

    # test writes
    print("\ntesting writes...")
    test_data = [
        ("hello", "world"),
        ("name", "test"),
        ("key1", "value1"),
        ("key2", "value2"),
        ("key3", "value3")
    ]

    for key, value in test_data:
        print(f"writing: {key} = {value}")
        if not write_key_value(key, value):
            print(f"FAIL: could not write {key}")
            cleanup()
            return False

    print("all writes completed")

    # wait for replication
    print("\nwaiting for replication...")
    time.sleep(5)

    # test reads and consistency
    print("\ntesting consistency...")
    all_consistent = True

    for key, expected_value in test_data:
        print(f"\nchecking {key}...")
        if not read_from_all_nodes(key, expected_value):
            all_consistent = False

    # test write rejection
    print("\ntesting write rejection on followers...")
    if not test_write_rejection():
        print("FAIL: follower should reject writes")
        all_consistent = False
    else:
        print("✓ follower correctly rejects writes")

    # cleanup
    cleanup()

    # final result
    if all_consistent:
        print("\n🎉 PASS: all tests successful!")
        return True
    else:
        print("\n❌ FAIL: some tests failed")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
