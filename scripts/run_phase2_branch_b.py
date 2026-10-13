#!/usr/bin/env python3
"""
scripts/run_phase2_branch_b.py

Automated orchestrator for Phase 2 (Control Batch) and Branch B (Dynamic Changing-Load Study).
Executes 23 interleaved runs in 3 balanced rounds:
  Phase 2:
    - Fixed-20k @ 500 kbps (3 runs)
    - Fixed-30k @ 500 kbps (3 runs)
    - Fixed-20k @ 200 kbps repeat (1 run)
    - Fixed-30k @ 1000 kbps repeat (1 run)
  Branch B (Dynamic schedule: 200k (233s) -> 1000k (233s) -> 500k (234s)):
    - Fixed-20k (3 runs)
    - Fixed-30k (3 runs)
    - Rule Controller (3 runs)
    - Base RL starting from 50k (infer, 3 runs)
    - Base RL starting from 20k floor (infer20k, 3 runs)

Total: 23 runs (~4.5 hours unattended execution).
Features:
  - Round interleaving to eliminate host/temporal drift bias.
  - Automatic validation and up to 2 retries per invalid slot.
  - Dedicated audit logging to src/logs/campaign_v2/phase2_branch_b.log.
"""

import sys
import time
import subprocess
from pathlib import Path

REPO_ROOT = Path("/home/p4/DESiRED")
RUNNER = REPO_ROOT / "scripts/run_experiment.py"
LOG_DIR = REPO_ROOT / "src/logs/campaign_v2"
BATCH_LOG = LOG_DIR / "phase2_branch_b.log"

DYN_SCHEDULE = "200:233,1000:233,500:234"

def build_queue():
    queue = []
    
    # Round 1
    queue.append({"run_id": "v2_ctrl_fixed20k_500k_1", "policy": "fixed20k", "load": 500, "schedule": None, "dur": 700, "round": 1})
    queue.append({"run_id": "v2_ctrl_fixed30k_500k_1", "policy": "fixed30k", "load": 500, "schedule": None, "dur": 700, "round": 1})
    queue.append({"run_id": "v2_ctrl_fixed20k_200k_rep", "policy": "fixed20k", "load": 200, "schedule": None, "dur": 700, "round": 1})
    queue.append({"run_id": "v2_dyn_fixed20k_1", "policy": "fixed20k", "load": None, "schedule": DYN_SCHEDULE, "dur": 700, "round": 1})
    queue.append({"run_id": "v2_dyn_fixed30k_1", "policy": "fixed30k", "load": None, "schedule": DYN_SCHEDULE, "dur": 700, "round": 1})
    queue.append({"run_id": "v2_dyn_rule_1", "policy": "rule", "load": None, "schedule": DYN_SCHEDULE, "dur": 700, "round": 1})
    queue.append({"run_id": "v2_dyn_infer50k_1", "policy": "infer", "load": None, "schedule": DYN_SCHEDULE, "dur": 700, "round": 1})
    queue.append({"run_id": "v2_dyn_infer20k_1", "policy": "infer20k", "load": None, "schedule": DYN_SCHEDULE, "dur": 700, "round": 1})

    # Round 2
    queue.append({"run_id": "v2_ctrl_fixed20k_500k_2", "policy": "fixed20k", "load": 500, "schedule": None, "dur": 700, "round": 2})
    queue.append({"run_id": "v2_ctrl_fixed30k_500k_2", "policy": "fixed30k", "load": 500, "schedule": None, "dur": 700, "round": 2})
    queue.append({"run_id": "v2_ctrl_fixed30k_1000k_rep", "policy": "fixed30k", "load": 1000, "schedule": None, "dur": 700, "round": 2})
    queue.append({"run_id": "v2_dyn_fixed20k_2", "policy": "fixed20k", "load": None, "schedule": DYN_SCHEDULE, "dur": 700, "round": 2})
    queue.append({"run_id": "v2_dyn_fixed30k_2", "policy": "fixed30k", "load": None, "schedule": DYN_SCHEDULE, "dur": 700, "round": 2})
    queue.append({"run_id": "v2_dyn_rule_2", "policy": "rule", "load": None, "schedule": DYN_SCHEDULE, "dur": 700, "round": 2})
    queue.append({"run_id": "v2_dyn_infer50k_2", "policy": "infer", "load": None, "schedule": DYN_SCHEDULE, "dur": 700, "round": 2})
    queue.append({"run_id": "v2_dyn_infer20k_2", "policy": "infer20k", "load": None, "schedule": DYN_SCHEDULE, "dur": 700, "round": 2})

    # Round 3
    queue.append({"run_id": "v2_ctrl_fixed20k_500k_3", "policy": "fixed20k", "load": 500, "schedule": None, "dur": 700, "round": 3})
    queue.append({"run_id": "v2_ctrl_fixed30k_500k_3", "policy": "fixed30k", "load": 500, "schedule": None, "dur": 700, "round": 3})
    queue.append({"run_id": "v2_dyn_fixed20k_3", "policy": "fixed20k", "load": None, "schedule": DYN_SCHEDULE, "dur": 700, "round": 3})
    queue.append({"run_id": "v2_dyn_fixed30k_3", "policy": "fixed30k", "load": None, "schedule": DYN_SCHEDULE, "dur": 700, "round": 3})
    queue.append({"run_id": "v2_dyn_rule_3", "policy": "rule", "load": None, "schedule": DYN_SCHEDULE, "dur": 700, "round": 3})
    queue.append({"run_id": "v2_dyn_infer50k_3", "policy": "infer", "load": None, "schedule": DYN_SCHEDULE, "dur": 700, "round": 3})
    queue.append({"run_id": "v2_dyn_infer20k_3", "policy": "infer20k", "load": None, "schedule": DYN_SCHEDULE, "dur": 700, "round": 3})

    return queue

def log_msg(msg):
    ts = time.strftime("[%Y-%m-%d %H:%M:%S]")
    line = f"{ts} {msg}"
    print(line, flush=True)
    with open(BATCH_LOG, "a") as f:
        f.write(line + "\n")

def execute_slot(item, max_retries=2):
    run_id = item["run_id"]
    pol = item["policy"]
    dur = item["dur"]
    load = item["load"]
    sched = item["schedule"]

    for attempt in range(max_retries + 1):
        attempt_id = run_id if attempt == 0 else f"{run_id}_retry{attempt}"
        sched_desc = f"Schedule: {sched}" if sched else f"Static Load: {load} kbps"
        log_msg(f"[*] Starting {attempt_id} (Policy: {pol}, {sched_desc}, Duration: {dur}s, Attempt: {attempt+1}/{max_retries+1})")

        cmd = [
            sys.executable,
            str(RUNNER),
            "--run-id", attempt_id,
            "--policy", pol,
            "--duration", str(dur)
        ]
        if sched:
            cmd.extend(["--load-schedule", sched])
        else:
            cmd.extend(["--load-kbps", str(load)])

        start_t = time.time()
        res = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
        elapsed = time.time() - start_t

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
    queue = build_queue()
    total_slots = len(queue)
    log_msg(f"==================================================")
    log_msg(f" Launching Phase 2 Control Batch & Branch B Study")
    log_msg(f" Total slots: {total_slots} runs (~{total_slots * 12 / 60:.1f} hours)")
    log_msg(f"==================================================")

    passed_count = 0
    start_total = time.time()

    for idx, item in enumerate(queue, 1):
        log_msg(f"\n--- Processing Slot {idx}/{total_slots}: {item['run_id']} (Round {item['round']}) ---")
        success = execute_slot(item)
        if success:
            passed_count += 1
        
        # Brief settling interval between runs
        time.sleep(15.0)

    total_elapsed = time.time() - start_total
    log_msg(f"\n==================================================")
    log_msg(f" Phase 2 & Branch B Campaign Completed!")
    log_msg(f" Slots Passed: {passed_count}/{total_slots}")
    log_msg(f" Total Time: {total_elapsed / 3600:.2f} hours")
    log_msg(f"==================================================")

if __name__ == "__main__":
    main()
