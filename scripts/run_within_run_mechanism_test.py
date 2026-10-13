#!/usr/bin/env python3
"""
scripts/run_within_run_mechanism_test.py

Implements Step 5: Within-Run Mechanism Test (Campaign v4).
Tests whether changing targetDelay_reg (20k vs 70k) alters dataplane behavior
(queue delay, queue depth, and switch drop/violation counters) while load is held constant.

Protocol:
  Total duration: 150 seconds per run
  - 0-30s:   Warmup / settle (Target = 20k, discarded from stats)
  - 30-70s:  Segment A (Target = 20k, 40s duration)
  - 70-110s: Segment B (Target = 70k, 40s duration)
  - 110-150s: Segment C (Target = 20k, 40s duration, tests reversibility)

Measurements recorded per segment:
  - INT queue delay on Switch 2 (median & IQR in ms)
  - INT queue depth on Switch 2 (median & mean in packets)
  - Switch 2 hardware counters: forwardingPkt, dropPkt, dropRecirc, recirc, cloneCount
  - Switch 2 registers: QDelay_reg (EWMA), dropProbability
"""

import sys
import time
import re
import subprocess
from pathlib import Path
import numpy as np
import pandas as pd

REPO_ROOT = Path("/home/p4/DESiRED")
LOG_DIR = REPO_ROOT / "src/logs/campaign_v4"
LOG_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR = REPO_ROOT / "results/campaign_v4"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_CSV = OUT_DIR / "mechanism_test_results.csv"

def snapshot_state():
    cmd = """counter_read forwardingPkt 2
counter_read dropPkt 2
counter_read recirc 2
counter_read dropRecirc 2
counter_read cloneCount 2
register_read MyEgress.QDelay_reg 2
register_read MyEgress.dropProbability 2
"""
    res = subprocess.run(
        f'echo "{cmd}" | simple_switch_CLI --thrift-port 9091',
        shell=True, capture_output=True, text=True
    )
    def parse_counter(name):
        m = re.search(rf"{name}\[2\]=\s*\(\d+\s+bytes,\s+(\d+)\s+packets\)", res.stdout)
        return int(m.group(1)) if m else 0

    def parse_reg(name):
        m = re.search(rf"{name}\[2\]=\s*(\d+)", res.stdout)
        return int(m.group(1)) if m else 0

    return {
        "fwd": parse_counter("forwardingPkt"),
        "drp": parse_counter("dropPkt"),
        "drec": parse_counter("dropRecirc"),
        "rec": parse_counter("recirc"),
        "cln": parse_counter("cloneCount"),
        "ewma": parse_reg("MyEgress.QDelay_reg"),
        "prob": parse_reg("MyEgress.dropProbability")
    }

def set_target_delay(target_us):
    for p in [9090, 9091, 9092]:
        subprocess.run(
            f"echo 'register_write MyEgress.targetDelay_reg 0 {target_us}' | simple_switch_CLI --thrift-port {p}",
            shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

def run_single_within_run_test(load_kbps, rep_idx):
    test_id = f"mech_{load_kbps}k_rep{rep_idx}"
    print(f"\n=======================================================")
    print(f"[*] Starting {test_id}: Load = {load_kbps} kbps, Rep = {rep_idx}")
    print(f"=======================================================")

    int_log = LOG_DIR / f"log_INT_{test_id}.txt"
    iperf_log = LOG_DIR / f"iperf_{test_id}.log"
    recv_log = LOG_DIR / f"recv_{test_id}.log"
    send_log = LOG_DIR / f"send_{test_id}.log"

    for p in [int_log, iperf_log, recv_log, send_log]:
        if p.exists():
            p.unlink()

    # Reset initial state: Target = 20k
    set_target_delay(20000)
    subprocess.run(
        "echo -e 'set_queue_rate 200 2\nset_queue_depth 32 2' | simple_switch_CLI --thrift-port 9091",
        shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    # Clean up any leftover background traffic on both sender and receiver hosts
    subprocess.run("mx h3 pkill -9 -f iperf3", shell=True)
    subprocess.run("mx h4 pkill -9 -f iperf3", shell=True)
    subprocess.run("mx h4 pkill -9 -f int_receiver", shell=True)
    subprocess.run("mx h1 pkill -9 -f int_sender", shell=True)
    time.sleep(0.5)

    # Start fresh iperf3 server on h4
    subprocess.run("mx h4 iperf3 -s -D", shell=True)
    time.sleep(0.5)

    # Start INT receiver on h4
    p_recv = subprocess.Popen(
        f"mx h4 python3 /home/p4/DESiRED/testbed/int_receiver_debug.py --iface h4-eth0 --out {int_log} > {recv_log} 2>&1",
        shell=True
    )
    time.sleep(0.5)

    # Start constant background traffic on h3 (300 seconds to guarantee full continuous coverage through Segment C)
    p_iperf = subprocess.Popen(
        f"mx h3 iperf3 -c 10.0.0.4 -u -b {load_kbps}k -t 300 -l 1470 -i 1 > {iperf_log} 2>&1",
        shell=True
    )
    time.sleep(0.5)

    # Start INT sender on h1 (300 probes at 1Hz)
    p_sender = subprocess.Popen(
        f"mx h1 python3 /home/p4/DESiRED/testbed/int_sender.py --src 10.0.0.1 --dst 10.0.0.4 --dst-mac 00:00:0a:00:00:04 --iface h1-eth0 --count 300 --interval 1.0 > {send_log} 2>&1",
        shell=True
    )

    # 1. Warmup (0-30s) at 20k
    print("  [Warmup 30s] Initial queue build-up (Target: 20k)...")
    time.sleep(30.0)

    # 2. Segment A (Target = 20k, 40.0s)
    print("  [Segment A] Steady Target = 20k (40s)...")
    tA_start = time.time()
    snap_A_start = snapshot_state()
    time.sleep(40.0)
    tA_end = time.time()
    snap_A_end = snapshot_state()

    # Transition to 70k
    print("  --> [SWITCH] Changing Target to 70k...")
    set_target_delay(70000)
    time.sleep(2.0)  # Settle time after register update

    # 3. Segment B (Target = 70k, 40.0s)
    print("  [Segment B] Steady Target = 70k (40s)...")
    tB_start = time.time()
    snap_B_start = snapshot_state()
    time.sleep(40.0)
    tB_end = time.time()
    snap_B_end = snapshot_state()

    # Transition back to 20k
    print("  --> [SWITCH] Changing Target back to 20k...")
    set_target_delay(20000)
    time.sleep(2.0)  # Settle time after register update

    # 4. Segment C (Target = 20k, 40.0s, reversibility check)
    print("  [Segment C] Steady Target = 20k (40s)...")
    tC_start = time.time()
    snap_C_start = snapshot_state()
    time.sleep(40.0)
    tC_end = time.time()
    snap_C_end = snapshot_state()

    # Stop traffic processes immediately after Segment C completes
    p_sender.terminate()
    p_iperf.terminate()
    subprocess.run("mx h3 pkill -9 -f iperf3", shell=True)
    subprocess.run("mx h4 pkill -9 -f iperf3", shell=True)
    subprocess.run("mx h4 pkill -9 -f int_receiver", shell=True)
    subprocess.run("mx h1 pkill -9 -f int_sender", shell=True)
    p_recv.terminate()
    time.sleep(1.0)

    # Parse INT telemetry for segments
    int_records = []
    if int_log.exists():
        lines = [l.strip().split(",") for l in int_log.read_text().splitlines() if l.strip()]
        if lines:
            t0 = int(lines[0][0])
            for parts in lines:
                if len(parts) >= 31:
                    try:
                        ts = int(parts[0]) / 1000.0  # Unix timestamp in seconds
                        deq_ms = int(parts[19]) / 1000.0
                        qdepth = int(parts[18])
                        int_records.append((ts, deq_ms, qdepth))
                    except (ValueError, IndexError):
                        pass

    def get_int_stats(ts_low, ts_high):
        sub = [d for (t, d, q) in int_records if ts_low <= t <= ts_high]
        sub_q = [q for (t, d, q) in int_records if ts_low <= t <= ts_high]
        if not sub:
            return 0.0, 0.0, 0.0, 0
        med = float(np.median(sub))
        iqr = float(np.percentile(sub, 75) - np.percentile(sub, 25)) if len(sub) > 1 else 0.0
        med_q = float(np.median(sub_q))
        return med, iqr, med_q, len(sub)

    segA_qmed, segA_qiqr, segA_qdep, segA_n = get_int_stats(tA_start, tA_end)
    segB_qmed, segB_qiqr, segB_qdep, segB_n = get_int_stats(tB_start, tB_end)
    segC_qmed, segC_qiqr, segC_qdep, segC_n = get_int_stats(tC_start, tC_end)

    # Independent segment counter deltas
    drp_A = snap_A_end["drp"] - snap_A_start["drp"]
    fwd_A = snap_A_end["fwd"] - snap_A_start["fwd"]
    total_A = drp_A + fwd_A

    drp_B = snap_B_end["drp"] - snap_B_start["drp"]
    fwd_B = snap_B_end["fwd"] - snap_B_start["fwd"]
    total_B = drp_B + fwd_B

    drp_C = snap_C_end["drp"] - snap_C_start["drp"]
    fwd_C = snap_C_end["fwd"] - snap_C_start["fwd"]
    total_C = drp_C + fwd_C

    # Traffic balance acceptance check across segments
    balance_B = abs(total_B - total_A) / max(1, total_A)
    balance_C = abs(total_C - total_A) / max(1, total_A)
    balanced = (balance_B <= 0.05) and (balance_C <= 0.05)

    print(f"\n[RESULTS {test_id}]:")
    print(f"  Segment A (Target 20k): Q-Delay = {segA_qmed:.2f} ms (IQR: {segA_qiqr:.2f}) | AQM Drops: {drp_A} | Fwd: {fwd_A} | Total: {total_A}")
    print(f"  Segment B (Target 70k): Q-Delay = {segB_qmed:.2f} ms (IQR: {segB_qiqr:.2f}) | AQM Drops: {drp_B} | Fwd: {fwd_B} | Total: {total_B}")
    print(f"  Segment C (Target 20k): Q-Delay = {segC_qmed:.2f} ms (IQR: {segC_qiqr:.2f}) | AQM Drops: {drp_C} | Fwd: {fwd_C} | Total: {total_C}")
    print(f"  --> Traffic Balance check: devB = {balance_B*100:.1f}%, devC = {balance_C*100:.1f}% -> {'PASSED' if balanced else 'WARNING: IMBALANCED'}")
    print(f"  --> Delta(B - A) Q-Delay: {segB_qmed - segA_qmed:+.2f} ms | Delta AQM Drops: {drp_B - drp_A:+d}")

    return [
        {
            "test_id": test_id, "load_kbps": load_kbps, "rep": rep_idx,
            "segment": "A", "target_ms": 20, "qdelay_median_ms": segA_qmed,
            "qdelay_iqr_ms": segA_qiqr, "qdepth_median": segA_qdep, "n_probes": segA_n,
            "red_drops": drp_A, "fwd_pkts": fwd_A, "total_pkts": total_A, "ewma_end_ms": snap_A_end["ewma"] / 1000.0
        },
        {
            "test_id": test_id, "load_kbps": load_kbps, "rep": rep_idx,
            "segment": "B", "target_ms": 70, "qdelay_median_ms": segB_qmed,
            "qdelay_iqr_ms": segB_qiqr, "qdepth_median": segB_qdep, "n_probes": segB_n,
            "red_drops": drp_B, "fwd_pkts": fwd_B, "total_pkts": total_B, "ewma_end_ms": snap_B_end["ewma"] / 1000.0
        },
        {
            "test_id": test_id, "load_kbps": load_kbps, "rep": rep_idx,
            "segment": "C", "target_ms": 20, "qdelay_median_ms": segC_qmed,
            "qdelay_iqr_ms": segC_qiqr, "qdepth_median": segC_qdep, "n_probes": segC_n,
            "red_drops": drp_C, "fwd_pkts": fwd_C, "total_pkts": total_C, "ewma_end_ms": snap_C_end["ewma"] / 1000.0
        }
    ]

def main():
    if len(sys.argv) > 1:
        loads = [int(x) for x in sys.argv[1:]]
    else:
        # Calibrated loads (70%, 80%, 90% of empirical 1650 kbps capacity)
        loads = [1150, 1320, 1485]

    all_rows = []
    print("=================================================================")
    print("CAMPAIGN v4: WITHIN-RUN MECHANISM TEST (N=3 repeats per load)")
    print(f"Calibrated target loads: {loads} kbps")
    print("=================================================================")

    for load in loads:
        for rep in [1, 2, 3]:
            rows = run_single_within_run_test(load, rep)
            all_rows.extend(rows)
            # Incremental save to prevent data loss
            pd.DataFrame(all_rows).to_csv(OUT_CSV, index=False)
            time.sleep(2.0)

    print(f"\n[+] Full mechanism test results saved to {OUT_CSV}")

if __name__ == "__main__":
    main()
