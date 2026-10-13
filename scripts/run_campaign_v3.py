#!/usr/bin/env python3
"""
scripts/run_campaign_v3.py

Automated orchestrator for Stage 3 & Stage 4 of the Reviewer Action Plan:
  - Stage 3: Fixed Delay Sweep under Congestion (fixed20k, fixed30k, fixed50k, fixed70k)
    - Low Load Condition: 1500 kbps (3 runs each = 12 runs)
    - Heavy Congestion Condition: 2600 kbps (5 runs each = 20 runs)
    - Tests if optimal target delay depends on condition beyond the Stage 1 noise floor (~3.5 FPS).
  - Stage 4: Controller Evaluation under Dynamic Schedule (1500k -> 2600k -> 1500k)
    - RL starting from 20k (infer20k, 5 runs)
    - RL starting from 50k (infer, 5 runs)
    - Rule-based controller (rule, 5 runs)

All runs are strictly interleaved across balanced rounds to prevent order/temporal bias.
Every run is validated immediately, recorded in experiment_registry.csv, and retry-protected.
"""

import sys
import time
import argparse
import subprocess
from pathlib import Path

REPO_ROOT = Path("/home/p4/DESiRED")
RUNNER = REPO_ROOT / "scripts/run_experiment.py"
LOG_DIR = REPO_ROOT / "src/logs/campaign_v2"
BATCH_LOG = LOG_DIR / "campaign_v3_orchestrator.log"

QUEUE_RATE = 200
QUEUE_DEPTH = 32
IPERF_HOST = "h3"
VIDEO_TARGET_MS = 60.0

def build_stage3_queue(duration=90):
    queue = []

    # =========================================================================
    # PART 1: STAGE 3 - Heavy Congestion Sweep (2600 kbps, 5 runs each, N=5)
    # Balanced Latin-Square interleaved order across 5 rounds
    # =========================================================================
    # Round 1
    queue.append({"run_id": "v3_cong_fixed20k_r1", "policy": "fixed20k", "load": 2600, "sched": None, "stage": "Stage 3 Heavy", "round": 1, "dur": duration})
    queue.append({"run_id": "v3_cong_fixed50k_r1", "policy": "fixed50k", "load": 2600, "sched": None, "stage": "Stage 3 Heavy", "round": 1, "dur": duration})
    queue.append({"run_id": "v3_cong_fixed30k_r1", "policy": "fixed30k", "load": 2600, "sched": None, "stage": "Stage 3 Heavy", "round": 1, "dur": duration})
    queue.append({"run_id": "v3_cong_fixed70k_r1", "policy": "fixed70k", "load": 2600, "sched": None, "stage": "Stage 3 Heavy", "round": 1, "dur": duration})

    # Round 2
    queue.append({"run_id": "v3_cong_fixed70k_r2", "policy": "fixed70k", "load": 2600, "sched": None, "stage": "Stage 3 Heavy", "round": 2, "dur": duration})
    queue.append({"run_id": "v3_cong_fixed30k_r2", "policy": "fixed30k", "load": 2600, "sched": None, "stage": "Stage 3 Heavy", "round": 2, "dur": duration})
    queue.append({"run_id": "v3_cong_fixed20k_r2", "policy": "fixed20k", "load": 2600, "sched": None, "stage": "Stage 3 Heavy", "round": 2, "dur": duration})
    queue.append({"run_id": "v3_cong_fixed50k_r2", "policy": "fixed50k", "load": 2600, "sched": None, "stage": "Stage 3 Heavy", "round": 2, "dur": duration})

    # Round 3
    queue.append({"run_id": "v3_cong_fixed30k_r3", "policy": "fixed30k", "load": 2600, "sched": None, "stage": "Stage 3 Heavy", "round": 3, "dur": duration})
    queue.append({"run_id": "v3_cong_fixed20k_r3", "policy": "fixed20k", "load": 2600, "sched": None, "stage": "Stage 3 Heavy", "round": 3, "dur": duration})
    queue.append({"run_id": "v3_cong_fixed70k_r3", "policy": "fixed70k", "load": 2600, "sched": None, "stage": "Stage 3 Heavy", "round": 3, "dur": duration})
    queue.append({"run_id": "v3_cong_fixed50k_r3", "policy": "fixed50k", "load": 2600, "sched": None, "stage": "Stage 3 Heavy", "round": 3, "dur": duration})

    # Round 4
    queue.append({"run_id": "v3_cong_fixed50k_r4", "policy": "fixed50k", "load": 2600, "sched": None, "stage": "Stage 3 Heavy", "round": 4, "dur": duration})
    queue.append({"run_id": "v3_cong_fixed70k_r4", "policy": "fixed70k", "load": 2600, "sched": None, "stage": "Stage 3 Heavy", "round": 4, "dur": duration})
    queue.append({"run_id": "v3_cong_fixed30k_r4", "policy": "fixed30k", "load": 2600, "sched": None, "stage": "Stage 3 Heavy", "round": 4, "dur": duration})
    queue.append({"run_id": "v3_cong_fixed20k_r4", "policy": "fixed20k", "load": 2600, "sched": None, "stage": "Stage 3 Heavy", "round": 4, "dur": duration})

    # Round 5
    queue.append({"run_id": "v3_cong_fixed20k_r5", "policy": "fixed20k", "load": 2600, "sched": None, "stage": "Stage 3 Heavy", "round": 5, "dur": duration})
    queue.append({"run_id": "v3_cong_fixed30k_r5", "policy": "fixed30k", "load": 2600, "sched": None, "stage": "Stage 3 Heavy", "round": 5, "dur": duration})
    queue.append({"run_id": "v3_cong_fixed50k_r5", "policy": "fixed50k", "load": 2600, "sched": None, "stage": "Stage 3 Heavy", "round": 5, "dur": duration})
    queue.append({"run_id": "v3_cong_fixed70k_r5", "policy": "fixed70k", "load": 2600, "sched": None, "stage": "Stage 3 Heavy", "round": 5, "dur": duration})

    # =========================================================================
    # PART 2: STAGE 3 - Low Load Baseline Sweep (1500 kbps, 3 runs each, N=3)
    # =========================================================================
    # Round 1
    queue.append({"run_id": "v3_low_fixed20k_r1", "policy": "fixed20k", "load": 1500, "sched": None, "stage": "Stage 3 Low", "round": 1, "dur": duration})
    queue.append({"run_id": "v3_low_fixed30k_r1", "policy": "fixed30k", "load": 1500, "sched": None, "stage": "Stage 3 Low", "round": 1, "dur": duration})
    queue.append({"run_id": "v3_low_fixed50k_r1", "policy": "fixed50k", "load": 1500, "sched": None, "stage": "Stage 3 Low", "round": 1, "dur": duration})
    queue.append({"run_id": "v3_low_fixed70k_r1", "policy": "fixed70k", "load": 1500, "sched": None, "stage": "Stage 3 Low", "round": 1, "dur": duration})

    # Round 2
    queue.append({"run_id": "v3_low_fixed70k_r2", "policy": "fixed70k", "load": 1500, "sched": None, "stage": "Stage 3 Low", "round": 2, "dur": duration})
    queue.append({"run_id": "v3_low_fixed50k_r2", "policy": "fixed50k", "load": 1500, "sched": None, "stage": "Stage 3 Low", "round": 2, "dur": duration})
    queue.append({"run_id": "v3_low_fixed30k_r2", "policy": "fixed30k", "load": 1500, "sched": None, "stage": "Stage 3 Low", "round": 2, "dur": duration})
    queue.append({"run_id": "v3_low_fixed20k_r2", "policy": "fixed20k", "load": 1500, "sched": None, "stage": "Stage 3 Low", "round": 2, "dur": duration})

    # Round 3
    queue.append({"run_id": "v3_low_fixed20k_r3", "policy": "fixed20k", "load": 1500, "sched": None, "stage": "Stage 3 Low", "round": 3, "dur": duration})
    queue.append({"run_id": "v3_low_fixed50k_r3", "policy": "fixed50k", "load": 1500, "sched": None, "stage": "Stage 3 Low", "round": 3, "dur": duration})
    queue.append({"run_id": "v3_low_fixed30k_r3", "policy": "fixed30k", "load": 1500, "sched": None, "stage": "Stage 3 Low", "round": 3, "dur": duration})
    queue.append({"run_id": "v3_low_fixed70k_r3", "policy": "fixed70k", "load": 1500, "sched": None, "stage": "Stage 3 Low", "round": 3, "dur": duration})

    return queue

def build_stage4_queue(duration=90):
    queue = []
    # Dynamic schedule: 3 equal segments of duration/3
    seg = duration // 3
    dyn_sched = f"1500:{seg},2600:{seg},1500:{duration - 2*seg}"

    for r in range(1, 6):
        order = [("rule", "rule"), ("infer20k", "infer20k"), ("infer", "infer")]
        if r % 2 == 0:
            order.reverse()
        for pol, pol_name in order:
            queue.append({
                "run_id": f"v3_dyn_{pol_name}_r{r}",
                "policy": pol,
                "load": None,
                "sched": dyn_sched,
                "stage": "Stage 4 Controller",
                "round": r,
                "dur": duration,
            })
    return queue

def execute_slot(item, retry=0):
    rid = item["run_id"]
    if retry > 0:
        rid = f"{rid}_retry{retry}"

    cmd = [
        sys.executable,
        str(RUNNER),
        "--run-id", rid,
        "--policy", item["policy"],
        "--duration", str(item["dur"]),
        "--iperf-host", IPERF_HOST,
        "--queue-rate", str(QUEUE_RATE),
        "--queue-depth", str(QUEUE_DEPTH),
        "--video-target-ms", str(VIDEO_TARGET_MS),
    ]

    if item["sched"]:
        cmd.extend(["--load-schedule", item["sched"]])
    else:
        cmd.extend(["--load-kbps", str(item["load"])])

    header = (
        f"\n{'='*70}\n"
        f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Launching {rid}\n"
        f"Stage: {item['stage']} | Policy: {item['policy']} | Round: {item['round']} | Retry: {retry}\n"
        f"Command: {' '.join(cmd)}\n"
        f"{'='*70}\n"
    )
    print(header)
    with open(BATCH_LOG, "a") as f:
        f.write(header)

    t0 = time.time()
    res = subprocess.run(cmd, cwd=REPO_ROOT, text=True, capture_output=True)
    elapsed = time.time() - t0

    log_entry = (
        f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Completed {rid} in {elapsed:.1f}s (Exit code: {res.returncode})\n"
        f"--- STDOUT ---\n{res.stdout}\n"
        f"--- STDERR ---\n{res.stderr}\n"
    )
    with open(BATCH_LOG, "a") as f:
        f.write(log_entry)
    print(f"[+] {rid} finished in {elapsed:.1f}s (Exit code: {res.returncode})")

    is_valid = "STATUS: VALID" in res.stdout or "[SUCCESS] Run" in res.stdout
    return is_valid, rid

def run_queue(queue, stage_name):
    total = len(queue)
    print(f"\n{'*'*70}")
    print(f"[*] Starting {stage_name}. Total slots: {total}")
    print(f"{'*'*70}\n")

    passed = 0
    failed = 0
    t_start = time.time()

    for idx, item in enumerate(queue, 1):
        print(f"\n>>> Slot {idx}/{total}: {item['run_id']} ({item['policy']}, {item['stage']}) <<<")
        success = False
        for attempt in range(3):
            valid, rid = execute_slot(item, retry=attempt)
            if valid:
                print(f"[SUCCESS] Slot {idx} ({rid}) verified VALID!")
                success = True
                passed += 1
                break
            else:
                print(f"[WARNING] Slot {idx} ({rid}) validation failed. Attempt {attempt + 1}/3.")
                time.sleep(5.0)

        if not success:
            print(f"[ERROR] Slot {idx} ({item['run_id']}) failed after 3 attempts.")
            failed += 1

        time.sleep(3.0)

    t_total = time.time() - t_start
    summary = (
        f"\n{'='*70}\n"
        f"{stage_name.upper()} COMPLETE\n"
        f"Total slots: {total} | Passed: {passed} | Failed: {failed}\n"
        f"Total Elapsed Time: {t_total/3600:.2f} hours ({t_total/60:.1f} minutes)\n"
        f"{'='*70}\n"
    )
    print(summary)
    with open(BATCH_LOG, "a") as f:
        f.write(summary)
    return passed, failed

def main():
    parser = argparse.ArgumentParser(description="Campaign V3 Orchestrator")
    parser.add_argument("--stage", choices=["3", "4", "all"], default="all", help="Stage to execute")
    parser.add_argument("--duration", type=int, default=90, help="Duration in seconds per run (default: 90)")
    args = parser.parse_args()

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    if args.stage in ("3", "all"):
        q3 = build_stage3_queue(duration=args.duration)
        run_queue(q3, "Stage 3 Fixed Sweep under Congestion")

    if args.stage in ("4", "all"):
        q4 = build_stage4_queue(duration=args.duration)
        run_queue(q4, "Stage 4 Controller Evaluation")

if __name__ == "__main__":
    main()
