#!/usr/bin/env python3
"""run all verification tests one by one"""

import subprocess
import sys
import time
import os

def run_command(command, description):
    """run a command and return success/failure"""
    print(f"\n{'='*60}")
    print(f"RUNNING: {description}")
    print(f"COMMAND: {command}")
    print('='*60)

    try:
        if command.startswith("python"):
            # run python scripts directly
            script_name = command.split()[-1]
            result = subprocess.run([sys.executable, script_name], timeout=600)
            return result.returncode == 0
        else:
            # run shell scripts or make commands
            result = subprocess.run(command, shell=True, timeout=600)
            return result.returncode == 0
    except subprocess.TimeoutExpired:
        print("TIMEOUT: command took too long")
        return False
    except Exception as e:
        print(f"ERROR: {str(e)}")
        return False

def main():
    """run all tests systematically"""
    print("=== DISTRIBUTED KEY-VALUE STORE VERIFICATION ===")
    print("Running all tests one by one...\n")

    tests = [
        ("python verify_setup.py", "Setup Verification (30s)"),
        ("./quick_test.sh", "Quick Test via Bash (2 min)"),
        ("python test_basic.py", "Basic Functionality Test (2 min)"),
        ("python integration_test.py", "Full Integration Test (5 min)"),
        ("python performance_analysis.py", "Performance Analysis (10+ min)")
    ]

    passed = 0
    total = len(tests)

    for i, (command, description) in enumerate(tests, 1):
        print(f"\n[{i}/{total}] {description}")
        if run_command(command, description):
            passed += 1
            print(f"✓ PASSED: {description}")
        else:
            print(f"❌ FAILED: {description}")

        # cleanup between tests
        print("\nCleaning up any leftover containers...")
        try:
            subprocess.run(["docker-compose", "down"], timeout=60, capture_output=True)
        except:
            pass

        if i < total:
            print(f"\nWaiting 5 seconds before next test...")
            time.sleep(5)

    print(f"\n{'='*60}")
    print(f"FINAL RESULTS: {passed}/{total} tests passed")
    print('='*60)

    if passed == total:
        print("🎉 ALL TESTS PASSED! The lab is working correctly.")
        return True
    else:
        print(f"❌ {total - passed} test(s) failed. Check the output above for details.")
        return False

if __name__ == "__main__":
    success = main()
    input("\nPress Enter to exit...")
    sys.exit(0 if success else 1)
