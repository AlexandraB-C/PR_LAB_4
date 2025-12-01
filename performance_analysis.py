#!/usr/bin/env python3
"""
performance analysis for distributed key-value store
tests quorums from 1 to 5, generates latency plots
"""

import asyncio
import requests
import time
import json
import subprocess
import sys
import matplotlib.pyplot as plt
import numpy as np
import concurrent.futures
from typing import Dict, List, Tuple, Optional
import statistics

# Service endpoints
SERVICES = {
    'leader': 'http://localhost:8000',
    'follower1': 'http://localhost:8001',
    'follower2': 'http://localhost:8002',
    'follower3': 'http://localhost:8003',
    'follower4': 'http://localhost:8004',
    'follower5': 'http://localhost:8005'
}

# Number of concurrent workers for writes
MAX_WORKERS = 10

def wait_for_services(timeout: int = 120) -> bool:
    """Wait for all services to be healthy"""
    print("Waiting for services to start...")
    start_time = time.time()

    while time.time() - start_time < timeout:
        all_healthy = True
        for name, url in SERVICES.items():
            try:
                response = requests.get(f"{url}/health", timeout=5)
                if response.status_code != 200:
                    all_healthy = False
                    break
            except Exception:
                all_healthy = False
                break

        if all_healthy:
            print("All services are healthy!")
            return True

        time.sleep(5)

    print("Timeout waiting for services to start")
    return False

def modify_docker_compose_quorum(new_quorum: int) -> bool:
    """Modify docker-compose.yml to set new quorum value"""
    try:
        with open('docker-compose.yml', 'r') as f:
            content = f.read()

        # Replace WRITE_QUORUM value
        old_line = '      - WRITE_QUORUM=3'
        new_line = f'      - WRITE_QUORUM={new_quorum}'
        modified_content = content.replace(old_line, new_line)

        with open('docker-compose.yml', 'w') as f:
            f.write(modified_content)

        print(f"Modified docker-compose.yml quorum to {new_quorum}")
        return True
    except Exception as e:
        print(f"Failed to modify docker-compose.yml: {e}")
        return False

def restart_services_with_new_quorum(quorum: int) -> bool:
    """Restart docker services with new quorum setting"""
    print(f"Restarting services with quorum {quorum}...")

    try:
        # Stop existing services
        subprocess.run(["docker-compose", "down"], check=True, timeout=60)

        # Modify configuration
        if not modify_docker_compose_quorum(quorum):
            return False

        # Start services with new configuration
        subprocess.run(["docker-compose", "up", "-d", "--build"],
                      check=True, timeout=300)

        # Wait for services to be ready
        if not wait_for_services():
            return False

        return True

    except subprocess.CalledProcessError as e:
        print(f"Failed to restart services: {e}")
        return False

def perform_write(key: str, value: str) -> Tuple[bool, float]:
    """Perform a single write operation and measure latency"""
    url = f"{SERVICES['leader']}/write"
    data = {"key": key, "value": value}
    start_time = time.time()

    try:
        response = requests.post(url, json=data, timeout=60)
        end_time = time.time()

        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                return True, end_time - start_time
        return False, end_time - start_time
    except Exception:
        return False, time.time() - start_time

def run_concurrent_writes(keys: List[str], quorum: int) -> List[Tuple[bool, float]]:
    """Run ~100 concurrent writes (10 at a time) on the given keys"""
    print(f"Running concurrent writes with quorum {quorum}...")

    results = []

    # Generate ~100 write operations (10 per key)
    operations = []
    for i in range(10):  # 10 writes per key
        for key in keys:
            value = f"value_{key}_{i}_{quorum}_{time.time()}"
            operations.append((key, value))

    # Run operations in batches of MAX_WORKERS
    total_operations = len(operations)
    completed = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit all operations as futures
        futures = [executor.submit(perform_write, key, value) for key, value in operations]

        # Collect results as they complete
        for future in concurrent.futures.as_completed(futures):
            success, latency = future.result()
            results.append((success, latency))
            completed += 1

            if completed % 10 == 0:
                print(f"Completed {completed}/{total_operations} writes...")

    return results

def verify_data_consistency(keys: List[str]) -> bool:
    """Verify data consistency across all replicas after writes complete"""
    print("Verifying data consistency across all replicas...")

    # Wait a bit for all replication to complete
    time.sleep(5)

    all_consistent = True

    for key in keys:
        print(f"Checking consistency for key '{key}'...")

        key_values = {}

        # Read from all nodes
        for node_name, url in SERVICES.items():
            try:
                response = requests.get(f"{url}/read/{key}", timeout=10)
                if response.status_code == 200:
                    result = response.json()
                    if result.get('found'):
                        key_values[node_name] = result.get('value')
                    else:
                        key_values[node_name] = None
                else:
                    key_values[node_name] = f"ERROR_{response.status_code}"
            except Exception as e:
                key_values[node_name] = f"EXCEPTION_{str(e)}"

        # Check consistency - all nodes should have the same value for each key
        values = list(key_values.values())
        if not all(v == values[0] for v in values):
            print(f"✗ Inconsistency detected for key '{key}': {key_values}")
            all_consistent = False
        else:
            print(f"✓ Key '{key}' is consistent")

    return all_consistent

def analyze_performance_results(results: Dict[int, List[Tuple[bool, float]]]) -> Dict[int, Dict]:
    """Analyze performance results and calculate statistics"""
    analysis = {}

    for quorum, latencies in results.items():
        successful_latencies = [latency for success, latency in latencies if success]
        failed_count = len(latencies) - len(successful_latencies)

        if successful_latencies:
            analysis[quorum] = {
                'success_rate': len(successful_latencies) / len(latencies),
                'avg_latency': statistics.mean(successful_latencies),
                'median_latency': statistics.median(successful_latencies),
                'min_latency': min(successful_latencies),
                'max_latency': max(successful_latencies),
                'successful_operations': len(successful_latencies),
                'failed_operations': failed_count
            }
        else:
            analysis[quorum] = {
                'success_rate': 0.0,
                'avg_latency': float('inf'),
                'median_latency': float('inf'),
                'min_latency': float('inf'),
                'max_latency': float('inf'),
                'successful_operations': 0,
                'failed_operations': failed_count
            }

    return analysis

def plot_results(analysis: Dict[int, Dict]) -> None:
    """Plot quorum vs average write latency"""
    quorums = sorted(analysis.keys())
    avg_latencies = [analysis[q]['avg_latency'] for q in quorums]
    success_rates = [analysis[q]['success_rate'] * 100 for q in quorums]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))

    # Plot latency
    ax1.plot(quorums, avg_latencies, 'bo-', linewidth=2, markersize=8)
    ax1.set_xlabel('Write Quorum')
    ax1.set_ylabel('Average Write Latency (seconds)')
    ax1.set_title('Write Quorum vs Average Latency')
    ax1.grid(True, alpha=0.3)

    # Add latency values on points
    for i, (q, latency) in enumerate(zip(quorums, avg_latencies)):
        ax1.annotate('.2f', (q, latency),
                    xytext=(10, 10), textcoords='offset points')

    # Plot success rate
    ax2.bar(quorums, success_rates, color='green', alpha=0.7)
    ax2.set_xlabel('Write Quorum')
    ax2.set_ylabel('Success Rate (%)')
    ax2.set_title('Write Quorum vs Success Rate')
    ax2.set_ylim(0, 100)
    ax2.grid(True, alpha=0.3)

    # Add success rate values on bars
    for i, (q, rate) in enumerate(zip(quorums, success_rates)):
        ax2.text(q, rate + 1, '0.1f', ha='center')

    plt.tight_layout()
    plt.savefig('performance_analysis.png', dpi=300, bbox_inches='tight')
    plt.show()

def explain_results(analysis: Dict[int, Dict]) -> None:
    """Explain observed results"""
    print("\n" + "="*80)
    print("PERFORMANCE ANALYSIS RESULTS EXPLANATION")
    print("="*80)

    quorums = sorted(analysis.keys())

    print("\nKEY OBSERVATIONS:")
    print("-" * 40)

    for quorum in quorums:
        data = analysis[quorum]
        success_rate = data['success_rate'] * 100
        avg_latency = data['avg_latency']

        print(f"Quorum {quorum}: Success Rate = {success_rate:.1f}%, Avg Latency = {avg_latency:.3f}s")

    print("\nANALYSIS:")
    print("-" * 40)

    # Analyze latency trends
    latencies = [analysis[q]['avg_latency'] for q in quorums]
    if latencies[0] < latencies[-1]:
        print("• Latency increases with higher quorum requirements")
        print("  This is expected because more confirmations are needed before acknowledging success")
    else:
        print("• Interestingly, latency doesn't strictly increase with quorum")
        print("  This might be due to network variability or caching effects")

    # Analyze success rate trends
    success_rates = [analysis[q]['success_rate'] for q in quorums]
    if success_rates[0] > success_rates[-1]:
        print("• Success rate tends to decrease with higher quorum requirements")
        print("  This suggests that requiring more confirmations makes failures more likely")
    else:
        print("• Success rate remains relatively stable across different quorums")

    print("\nFACTORS AFFECTING PERFORMANCE:")
    print("-" * 40)
    print("• Network latency: Each additional confirmation requires network round trips")
    print("• Replication delays: Configured delays (MIN_DELAY/MAX_DELAY) add variance")
    print("• Concurrent operations: Competing for network and compute resources")
    print("• Node failures: Any follower becoming unresponsive affects quorum achievement")
    print("• Threading/asynchronous processing: Concurrent request handling capacity")

    print("\nDATA CONSISTENCY:")
    print("-" * 40)
    print("• Eventual consistency is achieved through semi-synchronous replication")
    print("• Writes are only acknowledged when quorum is met")
    print("• Replication happens concurrently to all followers for efficiency")
    print("• Random delays simulate real-world network conditions")

    print("\nRECOMMENDATIONS:")
    print("-" * 40)
    print("• For high availability: Use quorum of 3 with 5 replicas (majority consensus)")
    print("• For low latency: Consider lower quorum but risk more data loss on failures")
    print("• For consistency: Higher quorum ensures more replicas have confirmed writes")
    print("• Monitor node health: Unhealthy followers can prevent quorum achievement")

def run_performance_analysis() -> bool:
    """Run the complete performance analysis"""
    print("Starting performance analysis...")

    # Define test keys
    test_keys = [f"perf_key_{i}" for i in range(10)]

    # Test different quorum values
    quorum_values = [1, 2, 3, 4, 5]
    results = {}

    try:
        for quorum in quorum_values:
            print(f"\n{'='*60}")
            print(f"TESTING WITH QUORUM {quorum}")
            print('='*60)

            # Restart services with new quorum
            if not restart_services_with_new_quorum(quorum):
                print(f"Failed to restart services with quorum {quorum}")
                return False

            # Run concurrent writes
            write_results = run_concurrent_writes(test_keys, quorum)
            results[quorum] = write_results

            successful_writes = sum(1 for success, _ in write_results if success)
            total_writes = len(write_results)
            success_rate = successful_writes / total_writes * 100

            print(f"Quorum {quorum} Results:")
            print(f"  Total writes: {total_writes}")
            print(f"  Successful: {successful_writes}")
            print(f"  Success rate: {success_rate:.1f}%")

            # Verify consistency
            if not verify_data_consistency(test_keys):
                print(f"✗ Data consistency check failed for quorum {quorum}")
                return False
            else:
                print(f"✓ Data consistency verified for quorum {quorum}")

        # Analyze and plot results
        analysis = analyze_performance_results(results)
        plot_results(analysis)

        # Explain results
        explain_results(analysis)

        print("\n*** Save the plot image as 'performance_analysis.png' for your report ***")

        return True

    finally:
        # Restore original quorum and cleanup
        print("\nRestoring original configuration...")
        try:
            modify_docker_compose_quorum(3)  # Restore default
            subprocess.run(["docker-compose", "down"], timeout=60)
        except Exception as e:
            print(f"Warning: Failed to cleanup: {e}")

if __name__ == "__main__":
    success = run_performance_analysis()
    if success:
        print("\n✓ Performance analysis completed successfully!")
    else:
        print("\n✗ Performance analysis failed!")
    sys.exit(0 if success else 1)
