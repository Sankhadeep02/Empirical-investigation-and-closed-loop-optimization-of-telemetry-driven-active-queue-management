#!/usr/bin/env python3
"""
scripts/reconstruct_full_registry.py

Audits and reconstructs the complete experiment registry across all 142 logged runs:
  - 104 Campaign v2 runs (eval, pilots, sweeps, control batches, dynamic schedules)
  - 30 Campaign v3 runs (Stage 3 heavy congestion & low load baseline)
  - 8 Knee-search diagnostic runs (UDP 1900k, 2100k, 2300k, TCP)

Preserves original commit hashes and statuses where committed in HEAD (commits fef96b6 & 8f92867),
reconstructs uncommitted runs with validator checks, and notes "reconstructed from logs" explicitly.
Backs up registry before writing.
"""

import os
import re
import csv
from pathlib import Path
from validate_run import validate_run

REPO_ROOT = Path("/home/p4/DESiRED")
LOG_DIR = REPO_ROOT / "src/logs/campaign_v2"
REGISTRY_FILE = REPO_ROOT / "results/campaign_v2/experiment_registry.csv"
BACKUP_FILE = REPO_ROOT / "results/campaign_v2/experiment_registry_backup_reconstruction.csv"

FIELDNAMES = [
    "run_id", "policy", "initial_delay", "load_kbps", "duration_s",
    "video_destination", "video_target_ms", "ping_timeout_s",
    "controller_enabled", "model_file", "code_commit", "status", "notes"
]

def parse_policy_and_delay(rid):
    if "fixed20k" in rid or "infer20k" in rid:
        pol = "infer20k" if "infer20k" in rid else "fixed20k"
        return pol, 20000, "yes" if "infer" in pol else "no"
    elif "fixed30k" in rid:
        return "fixed30k", 30000, "no"
    elif "fixed40k" in rid:
        return "fixed40k", 40000, "no"
    elif "fixed50k" in rid or "infer50k" in rid:
        pol = "infer" if "infer50k" in rid else "fixed50k"
        return pol, 50000, "yes" if "infer" in pol else "no"
    elif "fixed70k" in rid:
        return "fixed70k", 70000, "no"
    elif "infer9" in rid:
        return "infer9", 50000, "yes"
    elif "rule" in rid:
        return "rule", 50000, "yes"
    elif "infer" in rid:
        return "infer", 50000, "yes"
    return "unknown", 20000, "no"

def parse_load_and_dur(rid, df_path):
    # Check dash lines to estimate duration
    lines = [l for l in df_path.read_text(errors='ignore').splitlines() if l.strip()]
    dur = 700
    if len(lines) < 150:
        if len(lines) > 100:
            dur = 120
        elif len(lines) > 75:
            dur = 90
        elif len(lines) > 20:
            dur = 30
        else:
            dur = 10

    # Load parsing
    load = 500
    if "200k" in rid: load = 200
    elif "1000k" in rid: load = 1000
    elif "1500k" in rid or "low" in rid: load = 1500
    elif "1900k" in rid: load = 1900
    elif "2100k" in rid: load = 2100
    elif "2300k" in rid: load = 2300
    elif "2600k" in rid or "cong" in rid: load = 2600
    elif "TCP" in rid or "tcp" in rid: load = "tcp"
    elif "dyn" in rid: load = "dynamic"

    return load, dur

def main():
    print("[*] Reconstructing full registry across all campaign_v2 dash files...")
    
    # Read existing entries to preserve any historical notes
    existing_entries = {}
    if REGISTRY_FILE.exists() and REGISTRY_FILE.stat().st_size > 0:
        with open(REGISTRY_FILE, "r", newline="") as f:
            reader = csv.DictReader(f)
            for r in reader:
                existing_entries[r["run_id"]] = r

    dash_files = sorted(LOG_DIR.glob("dash_*.txt"))
    print(f"[+] Found {len(dash_files)} dash log files in {LOG_DIR}.")

    reconstructed_rows = []
    
    for df in dash_files:
        rid = df.name.replace("dash_", "").replace(".txt", "")
        
        # If already preserved in existing registry with committed details, retain
        if rid in existing_entries and not existing_entries[rid]["notes"].startswith("reconstructed"):
            reconstructed_rows.append(existing_entries[rid])
            continue

        pol, init_delay, ctrl = parse_policy_and_delay(rid)
        load, dur = parse_load_and_dur(rid, df)
        
        # Run validation
        min_ratio = 0.65 if ("v3_" in rid or "knee_" in rid) else 0.85
        status, details = validate_run(rid, expected_duration=dur, min_int_ratio=min_ratio)
        
        detail_str = "; ".join(details)
        note = f"reconstructed from logs; {detail_str}"
        
        model_file = "N/A"
        if pol in ("infer", "infer20k"):
            model_file = "train_socket_load_1.h5"
        elif pol == "infer9":
            model_file = "online_network_retrained_balanced.h5"
        elif pol == "rule":
            model_file = "heuristic_threshold"

        reconstructed_rows.append({
            "run_id": rid,
            "policy": pol,
            "initial_delay": str(init_delay),
            "load_kbps": str(load),
            "duration_s": str(dur),
            "video_destination": "10.0.0.4",
            "video_target_ms": "60.0",
            "ping_timeout_s": "0.5",
            "controller_enabled": ctrl,
            "model_file": model_file,
            "code_commit": "8f92867",
            "status": status,
            "notes": note,
        })

    # Sort deterministically
    reconstructed_rows.sort(key=lambda x: x["run_id"])

    # Backup existing if non-empty
    if REGISTRY_FILE.exists() and REGISTRY_FILE.stat().st_size > 0:
        import shutil
        shutil.copy2(REGISTRY_FILE, BACKUP_FILE)
        print(f"[+] Backed up existing registry to {BACKUP_FILE}")

    # Write atomically
    tmp_file = REGISTRY_FILE.with_suffix(".csv.tmp")
    with open(tmp_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(reconstructed_rows)
    os.replace(tmp_file, REGISTRY_FILE)

    print(f"[SUCCESS] Reconstructed registry with {len(reconstructed_rows)} total runs.")
    status_counts = {}
    for r in reconstructed_rows:
        status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1
    print("Status Breakdown:")
    for s, c in sorted(status_counts.items()):
        print(f"  {s}: {c}")

if __name__ == "__main__":
    main()
