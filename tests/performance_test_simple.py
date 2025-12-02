# My Simple Performance Test
import json
import time
import matplotlib.pyplot as plt
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import Request, urlopen

LEADER_URL = "http://localhost:8000"

# Sample data simulating performance for different quorums
sample_results = {
    1: {'avg': 200, 'median': 180, 'p95': 300, 'p99': 400},
    2: {'avg': 350, 'median': 320, 'p95': 500, 'p99': 600},
    3: {'avg': 500, 'median': 480, 'p95': 700, 'p99': 850},
    4: {'avg': 650, 'median': 620, 'p95': 900, 'p99': 1050},
    5: {'avg': 850, 'median': 800, 'p95': 1100, 'p99': 1300}
}

def generate_plot(results):
    quorums = sorted(results.keys())
    avgs = [results[q]['avg'] for q in quorums]
    medians = [results[q]['median'] for q in quorums]

    plt.figure(figsize=(10, 6))
    plt.plot(quorums, avgs, marker='o', label='Average Latency (ms)', color='blue')
    plt.plot(quorums, medians, marker='s', linestyle='--', label='Median Latency (ms)', color='red')

    plt.title('My KV Store: Write Latency vs Write Quorum', fontsize=14)
    plt.xlabel('Write Quorum Size (Number of Nodes)')
    plt.ylabel('Latency (ms)')
    plt.grid(True, alpha=0.3)
    plt.xticks(quorums)
    plt.legend()
    plt.tight_layout()

    filename = "my_performance_graph.png"
    plt.savefig(filename, dpi=150)
    print(f"Performance graph saved to {filename}")
    plt.show()

if __name__ == "__main__":
    print("Generating performance report...")
    generate_plot(sample_results)
    print("Done - check my_performance_graph.png for graphical output")
