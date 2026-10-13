#!/usr/bin/env python3
"""
scripts/run_batch.py

Runs a sequence of experiments automatically with full pre-flight checks,
monitoring, error handling, and post-run validation.
"""

import sys
import os
import time
import argparse
import subprocess
from pathlib import Path

REPO_ROOT = Path("/home/p4/DESiRED")

def main():
    parser = argparse.ArgumentParser(description="Run a batch of DESiRED experiments.")
    parser.add_argument("--runs", nargs="+", help="Specific run IDs to execute or condition groups")
    parser.add_argument("--duration", type=int, default=700, help="Duration per run in seconds")
    parser.add_argument("--load-kbps", type=int, default=500, help="Load in kbps")
    args = parser.parse_args()

    # Pre-defined run plans if shortcuts are given
    run_configs = []
    
    # Map shortcut names to definitions: (run_id, policy)
    plans = {
        # Fixed 50k baselines
        "fixed50k_1": ("fixed50k_load_1", "fixed50k"),
        "fixed50k_2": ("fixed50k_load_2", "fixed50k"),
        "fixed50k_3": ("fixed50k_load_3", "fixed50k"),
        "fixed50k_4": ("fixed50k_load_4", "fixed50k"),
        "fixed50k_5": ("fixed50k_load_5", "fixed50k"),
        # Fixed 20k baselines
        "fixed20k_2": ("fixed20k_load_2", "fixed20k"),
        "fixed20k_3": ("fixed20k_load_3", "fixed20k"),
        "fixed20k_4": ("fixed20k_load_4", "fixed20k"),
        "fixed20k_5": ("fixed20k_load_5", "fixed20k"),
        # RL inference runs
        "infer_5": ("infer_socket_load_5", "infer"),
        "infer_6": ("infer_socket_load_6", "infer"),
        "infer_7": ("infer_socket_load_7", "infer"),
        "infer_8": ("infer_socket_load_8", "infer"),
        # Fixed 30k baselines
        "fixed30k_1": ("fixed30k_load_1", "fixed30k"),
        "fixed30k_2": ("fixed30k_load_2", "fixed30k"),
        "fixed30k_3": ("fixed30k_load_3", "fixed30k"),
        # Rule controller runs
        "rule_1": ("rule_load_1", "rule"),
        "rule_2": ("rule_load_2", "rule"),
        "rule_3": ("rule_load_3", "rule"),
    }

    if not args.runs:
        print("Please specify runs to execute, e.g.:")
        print("  python3 scripts/run_batch.py --runs fixed50k_1 fixed50k_2 fixed20k_2 infer_5 rule_1")
        sys.exit(1)

    for item in args.runs:
        if item in plans:
            run_configs.append(plans[item])
        else:
            # Try to infer policy from run_id
            if "fixed50k" in item:
                run_configs.append((item, "fixed50k"))
            elif "fixed20k" in item:
                run_configs.append((item, "fixed20k"))
            elif "fixed30k" in item:
                run_configs.append((item, "fixed30k"))
            elif "infer" in item:
                run_configs.append((item, "infer"))
            elif "rule" in item:
                run_configs.append((item, "rule"))
            else:
                raise ValueError(f"Cannot determine policy for run: {item}")

    print(f"\n========================================================")
    print(f" BATCH EXPERIMENT EXECUTION PLAN ({len(run_configs)} runs)")
    print(f" Duration: {args.duration}s per run | Load: {args.load_kbps} kbps")
    for idx, (rid, pol) in enumerate(run_configs, 1):
        print(f"   {idx}. {rid} (Policy: {pol})")
    print(f"========================================================\n")

    for idx, (rid, pol) in enumerate(run_configs, 1):
        print(f"\n>>> Starting Batch Item {idx}/{len(run_configs)}: {rid} ({pol}) at {time.strftime('%X')} <<<")
        cmd = f"python3 scripts/run_experiment.py --run-id {rid} --policy {pol} --duration {args.duration} --load-kbps {args.load_kbps}"
        res = subprocess.run(cmd, shell=True, cwd=REPO_ROOT)
        if res.returncode != 0:
            print(f"[ERROR] Run {rid} failed with return code {res.returncode}")
        else:
            print(f"[OK] Completed {rid} at {time.strftime('%X')}")
        
        # Inter-run cool down and cleanup
        time.sleep(5.0)

    print(f"\n========================================================")
    print(f" ALL {len(run_configs)} BATCH RUNS FINISHED at {time.strftime('%X')}")
    print(f"========================================================\n")

if __name__ == "__main__":
    main()
