# Simplified Performance Tester for My KV Store
import json
import statistics
import time
import matplotlib.pyplot as plt
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import Request, urlopen

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPOSE_PATH = os.path.join(BASE_DIR, "docker-compose.yml")

LEADER_URL = "http://localhost:8000"

nr_writes = 100
nr_keys = 100
NUM_THREADS = 15

latencies = []
failures = 0
lock = threading.Lock()
thread_local = threading.local()


def get_session():
    if not hasattr(thread_local, "session"):
        thread_local.session = requests.Session()
    return thread_local.session


def reset():
    global latencies, failures
    with lock:
        latencies = []
        failures = 0


def record_latency(ms):
    with lock:
        latencies.append(ms)


def record_failure():
    global failures
    with lock:
        failures += 1


def measure_put_latency(key, value):
    url = f"{LEADER_URL}/kv/{key}"
    session = get_session()

    start = time.time()
    try:
        response = session.put(url, json={"value": value}, timeout=5)
        latency = (time.time() - start) * 1000

        if response.status_code == 200:
            return latency, response.json()
        return latency, None
    except Exception:
        latency = (time.time() - start) * 1000
        return latency, None


def perform_writes():
    reset()
    print(f"Starting {nr_writes} writes with {NUM_THREADS} threads...")

    def task(i):
        key = f"k{i % nr_keys}"
        val = f"v{i}"
        latency, res = measure_put_latency(key, val)
        if res and res.get("status") == "ok":
            record_latency(latency)
        else:
            record_failure()

    start = time.time()

    with ThreadPoolExecutor(max_workers=NUM_THREADS) as ex:
        write_tasks = [ex.submit(task, i) for i in range(nr_writes)]
        done = 0
        for _ in as_completed(write_tasks):
            done += 1
            if done % 500 == 0:
                print(f" Progress: {done}/{nr_writes}")

    total_time = time.time() - start

    if latencies:
        sorted_lat = sorted(latencies)
        avg_lat = statistics.mean(latencies)

        stats = {
            "avg": avg_lat,
            "median": statistics.median(latencies),
            "p95": sorted_lat[int(len(sorted_lat) * 0.95)],
            "p99": sorted_lat[int(len(sorted_lat) * 0.99)],
            "count": len(latencies),
            "failures": failures,
            "throughput": nr_writes / total_time
        }
    else:
        stats = {"avg": 0, "median": 0, "p95": 0, "p99": 0, "failures": nr_writes}

    return stats


def read_from_container(container, key):
    cmd = f"docker exec {container} curl -s http://localhost:8080/kv/{key}"
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout:
            try:
                return json.loads(result.stdout)
            except:
                return None
        return None
    except Exception:
        return None


def consistency_check():
    print("\nChecking consistency ...")
    containers = ["leader", "f1", "f2", "f3", "f4", "f5"]
    all_keys = [f"k{i}" for i in range(nr_keys)]
    results = {k: {} for k in all_keys}

    def read_key_from_container(container, key):
        data = read_from_container(container, key)
        return container, key, data

    with ThreadPoolExecutor(max_workers=50) as ex:
        read_tasks = []
        for c in containers:
            for k in all_keys:
                read_tasks.append(ex.submit(read_key_from_container, c, k))

        for f in as_completed(read_tasks):
            c, k, data = f.result()
            results[k][c] = data

    mismatches = 0
    missing = 0

    for k in all_keys:
        leader_data = results[k].get("leader")
        if not leader_data: continue

        leader_ver = leader_data["version"]

        for f in ["f1", "f2", "f3", "f4", "f5"]:
            f_data = results[k].get(f)
            if not f_data or "version" not in f_data:
                missing += 1
            elif f_data["version"] != leader_ver:
                mismatches += 1

    print(f" Missing keys: {missing}")
    print(f" Version mismatches: {mismatches}")
    return missing, mismatches


def update_quorum(quorum):
    with open(COMPOSE_PATH, "r") as f:
        txt = f.read()
    import re
    txt = re.sub(r'WRITE_QUORUM: "\d+"', f'WRITE_QUORUM: "{quorum}"', txt)
    with open(COMPOSE_PATH, "w") as f:
        f.write(txt)


def restart(quorum):
    print(f"\n--- SETTING UP QUORUM {quorum} ---")
    update_quorum(quorum)

    subprocess.run(["docker", "compose", "down"], capture_output=True)

    subprocess.run(["docker", "compose", "up", "-d"], capture_output=True)

    print("Waiting for leader startup...")
    time.sleep(3)

    session = requests.Session()
    for _ in range(30):
        try:
            response = session.get(f"{LEADER_URL}/health", timeout=1)
            if response.status_code == 200:
                print(" Leader ready.")
                return True
        except:
            time.sleep(1)

    print(" Leader NOT ready.")
    return False


def generate_graph(results):
    print("\nGenerating Graph...")
    quorums = sorted(results.keys())

    avgs = [results[q]['avg'] for q in quorums]
    medians = [results[q]['median'] for q in quorums]
    p95s = [results[q]['p95'] for q in quorums]
    p99s = [results[q]['p99'] for q in quorums]

    plt.figure(figsize=(12, 8))

    plt.plot(quorums, avgs, marker='o', label='Mean (Avg)')
    plt.plot(quorums, medians, marker='s', linestyle='--', label='Median')
    plt.plot(quorums, p95s, marker='^', linestyle='-.', label='p95 (95th Percentile)')
    plt.plot(quorums, p99s, marker='x', linestyle=':', label='p99 (99th Percentile)')

    plt.title("Write Quorum vs Latency Metrics")
    plt.xlabel("Write Quorum Size (Nodes)")
    plt.ylabel("Latency (ms)")
    plt.grid(True)
    plt.xticks(quorums)

    plt.legend()

    filename = "latency_graph.png"
    plt.savefig(filename)
    print(f" Graph saved to {filename}")

    try:
        os.startfile(filename)
    except:
        pass


def run_analysis():
    all_results = {}

    for q in [1, 2, 3, 4, 5]:
        if not restart(q):
            print(f"Skipping Quorum {q} due to failure")
            continue

        stats = perform_writes()
        all_results[q] = stats

        print(f" -> Result Q={q}: Avg={stats['avg']:.2f}ms, Failures={stats['failures']}")

        time.sleep(2)
        consistency_check()

    print("\nFinal Results Summary:")
    print(json.dumps(all_results, indent=2))

    generate_graph(all_results)


if __name__ == "__main__":
    run_analysis()
