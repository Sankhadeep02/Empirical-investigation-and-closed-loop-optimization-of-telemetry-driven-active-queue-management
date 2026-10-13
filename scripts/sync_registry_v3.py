#!/usr/bin/env python3
"""
scripts/sync_registry_v3.py
Synchronizes all completed v3 runs into results/campaign_v2/experiment_registry.csv.
"""

import re
import csv
from pathlib import Path
from validate_run import validate_run

REPO_ROOT = Path("/home/p4/DESiRED")
LOG_DIR = REPO_ROOT / "src/logs/campaign_v2"
REGISTRY_FILE = REPO_ROOT / "results/campaign_v2/experiment_registry.csv"

def sync():
    dash_files = sorted(LOG_DIR.glob("dash_v3_*.txt"))
    print(f"[*] Found {len(dash_files)} v3 dash files.")
    
    # Read existing registry
    existing = {}
    fieldnames = [
        "run_id", "policy", "initial_delay", "load_kbps", "duration_s",
        "video_destination", "video_target_ms", "ping_timeout_s",
        "controller_enabled", "model_file", "code_commit", "status", "notes"
    ]
    if REGISTRY_FILE.exists():
        with open(REGISTRY_FILE, "r", newline="") as f:
            reader = csv.DictReader(f)
            for r in reader:
                existing[r["run_id"]] = r

    commit_hash = "unknown"
    import subprocess
    try:
        commit_hash = subprocess.check_output("git rev-parse --short HEAD", shell=True, text=True, cwd=REPO_ROOT).strip()
    except Exception:
        pass

    for df in dash_files:
        rid = df.name.replace("dash_", "").replace(".txt", "")
        # Parse policy and load
        pol = "fixed20k"
        if "fixed30k" in rid: pol = "fixed30k"
        elif "fixed50k" in rid: pol = "fixed50k"
        elif "fixed70k" in rid: pol = "fixed70k"
        
        delay_map = {"fixed20k": 20000, "fixed30k": 30000, "fixed50k": 50000, "fixed70k": 70000}
        initial_delay = delay_map.get(pol, 20000)
        load = 2600 if "cong" in rid else 1500
        dur = 90

        status, details = validate_run(rid, expected_duration=dur, min_int_ratio=0.65)
        notes = "; ".join(details)
        
        existing[rid] = {
            "run_id": rid,
            "policy": pol,
            "initial_delay": str(initial_delay),
            "load_kbps": str(load),
            "duration_s": str(dur),
            "video_destination": "10.0.0.4",
            "video_target_ms": "60.0",
            "ping_timeout_s": "0.5",
            "controller_enabled": "no",
            "model_file": "N/A",
            "code_commit": commit_hash,
            "status": status,
            "notes": notes,
        }

    # Write back
    tmp = REGISTRY_FILE.with_suffix(".csv.tmp")
    with open(tmp, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(existing.values())
    import os
    os.replace(tmp, REGISTRY_FILE)
    print(f"[+] Synced {len(existing)} runs into {REGISTRY_FILE}.")

if __name__ == "__main__":
    sync()
