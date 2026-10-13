#!/usr/bin/env python3
"""
scripts/validate_run.py

Automated validator for DESiRED testbed experiment runs.
Verifies data integrity, duration, telemetry pairing, network load,
and controller execution for publishable experiments.

Status outcomes:
  VALID
  INVALID_NETWORK_LOAD
  INVALID_INT_CAPTURE
  INVALID_DASH_DURATION
  INVALID_CONTROLLER_EXIT
  INVALID_CONFIG
"""

import sys
import os
import argparse
from pathlib import Path
import re

LOG_DIR = Path("/home/p4/DESiRED/src/logs/campaign_v2")
AGENT_LOG_DIR = Path("/home/p4/DESiRED/local_controller/agent_logs/campaign_v2")

def validate_run(run_id, expected_duration=700, max_dash_gap=8.5, min_int_ratio=0.65, is_controller=None):
    details = []
    
    # Auto-detect if controller was expected if not explicitly specified
    if is_controller is None:
        if (
            run_id.startswith("infer_")
            or run_id.startswith("train_")
            or run_id.startswith("online_")
            or run_id.startswith("rule_")
            or run_id.startswith("v2_infer_")
            or run_id.startswith("v2_infer9_")
            or run_id.startswith("infer9_")
            or run_id.startswith("v2_rule_")
            or "_rule" in run_id
            or "_infer" in run_id
        ):
            is_controller = True
        else:
            is_controller = False

    # 1. Check iperf client log
    iperf_file = LOG_DIR / f"iperf_client_{run_id}.log"
    if not iperf_file.exists():
        details.append(f"Missing iperf client log: {iperf_file}")
        return "INVALID_NETWORK_LOAD", details
    
    iperf_content = iperf_file.read_text(errors='ignore')
    if "Connection refused" in iperf_content or "error - unable to connect" in iperf_content:
        details.append("iperf connection refused or failed to connect.")
        return "INVALID_NETWORK_LOAD", details
    
    if "iperf Done." not in iperf_content:
        details.append("iperf log does not contain 'iperf Done.'. Run terminated early.")
        return "INVALID_NETWORK_LOAD", details
    
    # Check for transfer volume
    match_transfer = re.search(r'(\d+\.?\d*)\s+MBytes', iperf_content)
    if not match_transfer and "KBytes" not in iperf_content:
        details.append("iperf transfer data missing or malformed.")
        return "INVALID_NETWORK_LOAD", details

    # 2. Check sender log
    sender_file = LOG_DIR / f"sender_{run_id}.log"
    expected_probes = expected_duration
    if sender_file.exists():
        sender_lines = [l for l in sender_file.read_text(errors='ignore').splitlines() if l.strip()]
        last_line = sender_lines[-1] if sender_lines else ""
        match_sender = re.search(r'\[(\d+)/(\d+)\]', last_line)
        if match_sender:
            sent_count = int(match_sender.group(1))
            total_count = int(match_sender.group(2))
            # Use the number of probes actually SENT as the expected total.
            # The sender is killed by cleanup_processes() at teardown, so
            # sent_count < total_count is normal, not a failure.
            expected_probes = sent_count if sent_count > 0 else total_count
            if sent_count < int(total_count * 0.70):
                # Only fail if sender barely started (< 70% sent)
                details.append(f"Sender aborted very early: only {sent_count}/{total_count} probes sent.")
                return "INVALID_INT_CAPTURE", details
            elif sent_count < total_count:
                details.append(f"Note: sender killed at teardown after {sent_count}/{total_count} probes (normal).")
        else:
            details.append(f"Sender log does not end with expected [N/N] probe line: {last_line}")
    else:
        # Note: some runs might have used stdout redirection differently
        details.append(f"Warning: sender log {sender_file} not found; proceeding to check INT log.")

    # 3. Check INT file
    int_file = LOG_DIR / f"log_INT_{run_id}.txt"
    if not int_file.exists():
        details.append(f"Missing INT log: {int_file}")
        return "INVALID_INT_CAPTURE", details
    
    int_lines = [l for l in int_file.read_text(errors='ignore').splitlines() if l.strip()]
    int_count = len(int_lines)
    min_probes = int(expected_probes * min_int_ratio)
    if int_count < min_probes:
        details.append(f"INT probe count too low: {int_count} received, expected at least {min_probes} ({min_int_ratio*100}% of {expected_probes}).")
        return "INVALID_INT_CAPTURE", details

    # 4. Check DASH file
    dash_file = LOG_DIR / f"dash_{run_id}.txt"
    if not dash_file.exists():
        details.append(f"Missing DASH log: {dash_file}")
        return "INVALID_DASH_DURATION", details

    dash_lines = [l for l in dash_file.read_text(errors='ignore').splitlines() if l.strip()]
    if len(dash_lines) < 10:
        details.append(f"DASH log has too few lines: {len(dash_lines)}")
        return "INVALID_DASH_DURATION", details

    timestamps = []
    for line in dash_lines:
        parts = line.split(";")
        if len(parts) >= 4:
            try:
                # Millisecond epoch timestamp
                ts_ms = int(parts[0])
                timestamps.append(ts_ms / 1000.0)
            except ValueError:
                continue

    if not timestamps:
        details.append("No valid timestamps found in DASH file.")
        return "INVALID_DASH_DURATION", details

    dash_duration = timestamps[-1] - timestamps[0]
    if dash_duration < (expected_duration - 30):
        details.append(f"DASH elapsed duration {dash_duration:.1f}s is less than threshold ({expected_duration - 30}s).")
        return "INVALID_DASH_DURATION", details

    # Check maximum gap between consecutive DASH samples
    max_gap = 0.0
    for i in range(1, len(timestamps)):
        gap = timestamps[i] - timestamps[i-1]
        if gap > max_gap:
            max_gap = gap

    if max_gap > max_dash_gap:
        details.append(f"DASH maximum inter-sample gap ({max_gap:.2f}s) exceeded limit of {max_dash_gap}s.")
        return "INVALID_DASH_DURATION", details

    # 5. Check Controller (for RL / Controller runs)
    if is_controller:
        ctrl_file = LOG_DIR / f"controller_{run_id}.log"
        if not ctrl_file.exists():
            details.append(f"Missing controller log: {ctrl_file}")
            return "INVALID_CONTROLLER_EXIT", details

        ctrl_content = ctrl_file.read_text(errors='ignore')
        if "Traceback (most recent call last):" in ctrl_content:
            details.append("Controller log contains unhandled Python Traceback.")
            return "INVALID_CONTROLLER_EXIT", details

        if "logs saved" not in ctrl_content:
            details.append("Controller log does not end with 'logs saved'.")
            return "INVALID_CONTROLLER_EXIT", details

        # Verify action history
        action_file = AGENT_LOG_DIR / f"action_history_{run_id}.csv"
        if not action_file.exists():
            details.append(f"Missing action history file: {action_file}")
            return "INVALID_CONTROLLER_EXIT", details

        action_lines = [l for l in action_file.read_text(errors='ignore').splitlines() if l.strip()]
        action_count = len(action_lines)
        min_actions = 20 if expected_duration >= 500 else 1
        if action_count < min_actions:
            details.append(f"Controller produced too few actions: {action_count} actions (minimum {min_actions} required for {expected_duration}s run).")
            return "INVALID_CONTROLLER_EXIT", details

        delay_file = AGENT_LOG_DIR / f"sw1_target_delay_history_{run_id}.csv"
        if not delay_file.exists():
            details.append(f"Missing sw1 target delay history file: {delay_file}")
            return "INVALID_CONTROLLER_EXIT", details

    # All checks passed!
    details.append(f"Duration: {dash_duration:.1f}s, INT probes: {int_count}, DASH rows: {len(dash_lines)}, Max DASH gap: {max_gap:.2f}s")
    return "VALID", details

def main():
    parser = argparse.ArgumentParser(description="Validate DESiRED experiment run logs.")
    parser.add_argument("run_id", help="Run ID (e.g. fixed20k_load_1, infer_socket_load_4)")
    parser.add_argument("--duration", type=int, default=700, help="Expected experiment duration in seconds")
    parser.add_argument("--min-int-ratio", type=float, default=0.65, help="Minimum ratio of INT probes required (default 0.65)")
    parser.add_argument("--controller", action="store_true", default=None, help="Force controller checks")
    parser.add_argument("--no-controller", dest="controller", action="store_false", help="Disable controller checks")
    args = parser.parse_args()

    status, details = validate_run(args.run_id, expected_duration=args.duration, min_int_ratio=args.min_int_ratio, is_controller=args.controller)
    print(f"RUN_ID: {args.run_id}")
    print(f"STATUS: {status}")
    for d in details:
        print(f"  - {d}")

    if status == "VALID":
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
