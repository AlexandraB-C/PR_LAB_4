#!/usr/bin/env python3
"""verify system setup for running the distributed key-value store"""

import subprocess
import sys
import socket
import requests
import importlib.util

def check_command(command, name, version_flag="--version"):
    """check if command exists and can run"""
    try:
        result = subprocess.run([command, version_flag], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            version = result.stdout.strip().split('\n')[0] if result.stdout.strip() else "unknown"
            print(f"✓ {name} found: {version}")
            return True
        else:
            print(f"❌ {name} command failed")
            return False
    except FileNotFoundError:
        print(f"❌ {name} not found in PATH")
        return False
    except Exception as e:
        print(f"❌ {name} check failed: {str(e)}")
        return False

def check_python_package(package_name, display_name):
    """check if python package is installed"""
    try:
        spec = importlib.util.find_spec(package_name.replace("-", "_"))
        if spec is not None:
            print(f"✓ {display_name} installed")
            return True
        else:
            print(f"❌ {display_name} not installed")
            return False
    except Exception as e:
        print(f"❌ {display_name} check failed: {str(e)}")
        return False

def check_port_available(port):
    """check if port is available (not in use)"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('127.0.0.1', port))
        sock.close()

        # result 0 means port is in use, which is bad for our setup
        if result == 0:
            print(f"❌ Port {port} is already in use")
            return False
        else:
            print(f"✓ Port {port} is available")
            return True
    except Exception as e:
        print(f"❌ Port {port} check failed: {str(e)}")
        return False

def check_docker_daemon():
    """check if docker daemon is running"""
    try:
        result = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and "Containers:" in result.stdout:
            print("✓ Docker daemon is running")
            return True
        else:
            print("❌ Docker daemon is not running")
            print("   Please start Docker Desktop or run 'sudo systemctl start docker'")
            return False
    except Exception as e:
        print("❌ Cannot check docker daemon status")
        return False

def check_internet():
    """check if internet connection is available"""
    try:
        response = requests.get("https://registry-1.docker.io", timeout=5)
        if response.status_code == 200:
            print("✓ Internet connection available")
            return True
        else:
            print("❌ Internet connection check failed")
            return False
    except:
        print("❌ No internet connection")
        return False

def main():
    """run all setup verifications"""
    print("=== SETUP VERIFICATION ===\n")

    all_good = True

    # check internet connection first
    print("Checking connectivity...")
    if not check_internet():
        all_good = False
    print()

    # check required commands
    print("Checking required tools...")
    tools = [
        ("docker", "Docker"),
        ("docker-compose", "Docker Compose", "version"),
        ("python", "Python", "--version"),
        ("pip", "Pip", "--version")
    ]

    for tool in tools:
        if len(tool) == 3:
            cmd, name, version_flag = tool
        else:
            cmd, name = tool
            version_flag = "--version"

        if not check_command(cmd, name, version_flag):
            all_good = False

    print()

    # check docker daemon
    print("Checking Docker daemon...")
    if not check_docker_daemon():
        all_good = False
    print()

    # check required python packages
    print("Checking Python packages...")
    packages = [
        ("fastapi", "FastAPI"),
        ("uvicorn", "Uvicorn"),
        ("pydantic", "Pydantic"),
        ("requests", "Requests"),
        ("matplotlib", "Matplotlib"),
        ("numpy", "NumPy")
    ]

    for package, display in packages:
        if not check_python_package(package, display):
            all_good = False

    print()

    # check ports availability
    print("Checking port availability...")
    ports = [8000, 8001, 8002, 8003, 8004, 8005]
    for port in ports:
        if not check_port_available(port):
            all_good = False

    print()

    # final result
    if all_good:
        print("🎉 ALL CHECKS PASSED!")
        print("Your system is ready to run the distributed key-value store.")
        print("\nTo start the system:")
        print("  make build && make up")
        print("  # or")
        print("  ./quick_test.sh")
        print("  # or")
        print("  python test_basic.py")
        return True
    else:
        print("❌ SOME CHECKS FAILED!")
        print("Please fix the issues above before running the system.")
        print("\nCommon fixes:")
        print("- Install Docker Desktop for your OS")
        print("- Start Docker Desktop")
        print("- Install missing Python packages: pip install -r requirements.txt")
        print("- Kill processes using ports 8000-8005")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
