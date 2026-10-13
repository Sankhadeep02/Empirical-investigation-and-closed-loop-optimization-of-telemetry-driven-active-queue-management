#!/usr/bin/env python3
"""
scripts/run_load_sweep.py

Automated orchestrator for the multi-load fixed-delay sweep campaign.
Executes fixed delays (20k, 30k, 40k, 50k, 70k) across 200 kbps and 1000 kbps (3 runs each),
plus fixed 70k at 500 kbps (3 runs), for a total of 33 runs (~7.5 hours).
Rounds are interleaved to eliminate time-of-day drift bias, with automatic
post-run validation and up to 2 retries per invalid slot.
"""

import sys
import time
import subprocess
from pathlib import Path

REPO_ROOT = Path("/home/p4/DESiRED")
RUNNER = REPO_ROOT / "scripts/run_experiment.py"
LOG_DIR = REPO_ROOT / "src/logs/campaign_v2"
SWEEP_LOG = LOG_DIR / "sweep_batch.log"

# Define the complete evaluation matrix
POLICIES = ["fixed20k", "fixed30k", "fixed40k", "fixed50k", "fixed70k"]
ROUNDS = [1, 2, 3]

def build_run_queue():
    queue = []
    # Interleave by round to prevent temporal drift
    for r in ROUNDS:
        # 1. 200 kbps runs
        for pol in POLICIES:
            run_id = f"v2_{pol}_200k_{r}"
            queue.append({
                "run_id": run_id,
                "policy": pol,
                "load": 200,
                "duration": 700,
                "round": r
            })
        # 2. 1000 kbps runs
        for pol in POLICIES:
            run_id = f"v2_{pol}_1000k_{r}"
            queue.append({
                "run_id": run_id,
                "policy": pol,
                "load": 1000,
                "duration": 700,
                "round": r
            })
        # 3. 500 kbps fixed70k run
        run_id = f"v2_fixed70k_500k_{r}"
        queue.append({
            "run_id": run_id,
            "policy": "fixed70k",
            "load": 500,
            "duration": 700,
            "round": r
        })
    return queue

def log_msg(msg):
    ts = time.strftime("[%Y-%m-%d %H:%M:%S]")
    line = f"{ts} {msg}"
    print(line)
    with open(SWEEP_LOG, "a") as f:
        f.write(line + "\n")

def execute_slot(item, max_retries=2):
    run_id = item["run_id"]
    pol = item["policy"]
    load = item["load"]
    dur = item["duration"]

    for attempt in range(max_retries + 1):
        attempt_id = run_id if attempt == 0 else f"{run_id}_retry{attempt}"
        log_msg(f"[*] Starting {attempt_id} (Policy: {pol}, Load: {load} kbps, Duration: {dur}s, Attempt: {attempt+1}/{max_retries+1})")
        
        cmd = [
            sys.executable,
            str(RUNNER),
            "--run-id", attempt_id,
            "--policy", pol,
            "--duration", str(dur),
            "--load-kbps", str(load)
        ]
        
        start_t = time.time()
        res = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
        elapsed = time.time() - start_t
        
        # Check validation output from runner
        if "[SUCCESS]" in res.stdout and "is VALID" in res.stdout:
            log_msg(f"[+] Slot {attempt_id} PASSED validation in {elapsed:.1f}s.")
            return True
        else:
            log_msg(f"[!] Slot {attempt_id} FAILED validation (Elapsed: {elapsed:.1f}s). Retrying...")
            time.sleep(10.0)

    log_msg(f"[-] Slot {run_id} exhausted all retries without valid status.")
    return False

def main():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    queue = build_run_queue()
    total_runs = len(queue)
    log_msg(f"==================================================")
    log_msg(f" Starting Automated Load Sweep Batch ({total_runs} runs)")
    log_msg(f"==================================================")
    
    passed = 0
    failed = 0
    start_batch = time.time()

    for idx, item in enumerate(queue, 1):
        log_msg(f"\n--- Progress: Run {idx}/{total_runs} ({(idx/total_runs)*100:.1f}%) ---")
        success = execute_slot(item)
        if success:
            passed += 1
        else:
            failed += 1
            
        time.sleep(5.0)  # Inter-run cool down

    total_time = (time.time() - start_batch) / 3600.0
    log_msg(f"\n==================================================")
    log_msg(f" Sweep Batch Completed in {total_time:.2f} hours")
    log_msg(f" Total Runs: {total_runs} | Valid: {passed} | Failed: {failed}")
    log_msg(f"==================================================")

if __name__ == "__main__":
    main()
