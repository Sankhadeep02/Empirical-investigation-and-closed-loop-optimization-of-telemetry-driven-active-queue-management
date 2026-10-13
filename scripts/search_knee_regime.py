#!/usr/bin/env python3
"""
scripts/search_knee_regime.py

Performs a systematic search for the operating knee where target-delay control matters.
Tests Fixed-20k vs Fixed-70k across:
  - UDP loads: 1900 kbps, 2100 kbps, 2300 kbps (~79%, 87%, 95% of 2.4 Mbps capacity)
  - TCP cross-traffic variant (responsive congestion control)
Duration: 90 seconds per test.

Outputs a structured comparison table showing whether:
  1. Queue delay follows target delay (20k vs 70k).
  2. Video FPS is sensitive (neither 0 FPS dead nor ceiling saturated at 30 FPS).
  3. Packet loss is moderate (>0% and <25%).
"""

import sys
import time
import subprocess
from pathlib import Path
import numpy as np
import pandas as pd

REPO_ROOT = Path("/home/p4/DESiRED")
RUNNER = REPO_ROOT / "scripts/run_experiment.py"
LOG_DIR = REPO_ROOT / "src/logs/campaign_v2"
OUT_CSV = REPO_ROOT / "results/campaign_v2/knee_search_results.csv"

QUEUE_RATE = 200
QUEUE_DEPTH = 32
DURATION = 90

TEST_CONDITIONS = [
    {"name": "UDP_1900k", "proto": "udp", "load": 1900},
    {"name": "UDP_2100k", "proto": "udp", "load": 2100},
    {"name": "UDP_2300k", "proto": "udp", "load": 2300},
    {"name": "TCP_flow",  "proto": "tcp", "load": 0},
]

def run_test(cond, policy):
    target_us = 20000 if policy == "fixed20k" else 70000
    rid = f"knee_{cond['name']}_{policy}"
    
    # 1. Clean previous logs for this run_id
    for pattern in [f"*{rid}*"]:
        for p in LOG_DIR.glob(pattern):
            p.unlink()

    dash_log = LOG_DIR / f"dash_{rid}.txt"
    int_log = LOG_DIR / f"log_INT_{rid}.txt"
    iperf_log = LOG_DIR / f"iperf_client_{rid}.log"
    video_log = LOG_DIR / f"video_{rid}.log"
    sender_log = LOG_DIR / f"sender_{rid}.log"
    receiver_log = LOG_DIR / f"receiver_{rid}.log"

    # Set switch registers and bottleneck shaping
    for port in [9090, 9091, 9092]:
        subprocess.run(f"echo 'register_write MyEgress.targetDelay_reg 0 {target_us}' | simple_switch_CLI --thrift-port {port}", shell=True, stdout=subprocess.DEVNULL)
    subprocess.run(f"echo 'set_queue_rate {QUEUE_RATE} 2\nset_queue_depth {QUEUE_DEPTH} 2' | simple_switch_CLI --thrift-port 9091", shell=True, stdout=subprocess.DEVNULL)
    time.sleep(1.0)

    # Start INT receiver on h4
    p_recv = subprocess.Popen(f"mx h4 python3 /home/p4/DESiRED/testbed/int_receiver_debug.py --iface h4-eth0 --out {int_log} > {receiver_log} 2>&1", shell=True)
    time.sleep(1.0)

    # Start traffic
    if cond["proto"] == "udp":
        iperf_cmd = f"mx h3 iperf3 -c 10.0.0.4 -u -b {cond['load']}k -t {DURATION} -i 1 -l 1470 > {iperf_log} 2>&1"
    else:
        # TCP responsive cross traffic
        iperf_cmd = f"mx h3 iperf3 -c 10.0.0.4 -t {DURATION} -i 1 > {iperf_log} 2>&1"
    p_iperf = subprocess.Popen(iperf_cmd, shell=True)

    # Video simulator on h1
    p_video = subprocess.Popen(f"mx h1 python3 /home/p4/DESiRED/testbed/video_simulator.py --dst 10.0.0.4 --target-delay-ms 60.0 --duration {DURATION} --out {dash_log} > {video_log} 2>&1", shell=True)

    # INT sender on h1
    p_sender = subprocess.Popen(f"mx h1 python3 /home/p4/DESiRED/testbed/int_sender.py --src 10.0.0.1 --dst 10.0.0.4 --dst-mac 00:00:0a:00:00:04 --iface h1-eth0 --count {DURATION} --interval 1.0 > {sender_log} 2>&1", shell=True)

    print(f"[*] Running {rid} ({cond['name']}, {policy}) for {DURATION}s...")
    p_video.wait()
    p_sender.wait()
    p_iperf.wait()
    p_recv.terminate()
    time.sleep(1.0)

    # Parse metrics
    fps_vals, buf_vals = [], []
    if dash_log.exists():
        for l in dash_log.read_text().splitlines():
            pts = l.strip().split(";")
            if len(pts) >= 4:
                buf_vals.append(float(pts[1]))
                fps_vals.append(float(pts[2]))

    deq2_vals, q2_vals = [], []
    if int_log.exists():
        for l in int_log.read_text().splitlines():
            pts = l.strip().split(",")
            if len(pts) >= 31:
                try:
                    deq2_vals.append(int(pts[19]))
                    q2_vals.append(int(pts[18]))
                except (ValueError, IndexError):
                    pass

    import re
    loss_pct = 0.0
    if iperf_log.exists():
        c = iperf_log.read_text(errors='ignore')
        m = re.findall(r"(\d+\.?\d*)%\s+receiver", c)
        if m:
            loss_pct = float(m[-1])

    mean_fps = float(np.mean(fps_vals)) if fps_vals else 0.0
    stalls = sum(1 for f in fps_vals if f == 0.0)
    stall_pct = (stalls / len(fps_vals) * 100.0) if fps_vals else 0.0
    mean_buf = float(np.mean(buf_vals)) if buf_vals else 0.0
    median_deq_ms = float(np.median(deq2_vals) / 1000.0) if deq2_vals else 0.0
    mean_qdepth = float(np.mean(q2_vals)) if q2_vals else 0.0

    print(f"[+] {rid}: FPS={mean_fps:.2f}, Stalls={stalls} ({stall_pct:.1f}%), Buffer={mean_buf:.2f}s, Hop2 Delay={median_deq_ms:.1f}ms, QDepth={mean_qdepth:.1f}pkts, Loss={loss_pct:.1f}%")
    return {
        "condition": cond["name"],
        "policy": policy,
        "mean_fps": mean_fps,
        "stall_pct": stall_pct,
        "stalls": stalls,
        "mean_buf_s": mean_buf,
        "hop2_qdelay_median_ms": median_deq_ms,
        "hop2_qdepth_mean_pkts": mean_qdepth,
        "loss_pct": loss_pct,
    }

def main():
    print("="*80)
    print("SEARCHING FOR THE KNEE REGIME (Fixed-20k vs Fixed-70k across loads and TCP)")
    print("="*80)
    
    results = []
    for cond in TEST_CONDITIONS:
        print(f"\n---> Testing Condition: {cond['name']} <---")
        res_20k = run_test(cond, "fixed20k")
        res_70k = run_test(cond, "fixed70k")
        results.append(res_20k)
        results.append(res_70k)
        time.sleep(3.0)

    df = pd.DataFrame(results)
    df.to_csv(OUT_CSV, index=False)
    print("\n" + "="*80)
    print("KNEE SEARCH SUMMARY RESULTS:")
    print("="*80)
    print(df.to_string(index=False))

    # Calculate differences between 20k and 70k for each condition
    print("\n" + "="*80)
    print("POLICY SEPARATION COMPARISON (Fixed-20k vs Fixed-70k):")
    print("="*80)
    for cond in TEST_CONDITIONS:
        cname = cond["name"]
        sub = df[df["condition"] == cname].set_index("policy")
        if "fixed20k" in sub.index and "fixed70k" in sub.index:
            r20 = sub.loc["fixed20k"]
            r70 = sub.loc["fixed70k"]
            fps_diff = r20["mean_fps"] - r70["mean_fps"]
            delay_diff = r20["hop2_qdelay_median_ms"] - r70["hop2_qdelay_median_ms"]
            print(f"Condition: {cname:<12} | FPS: 20k={r20['mean_fps']:5.2f} vs 70k={r70['mean_fps']:5.2f} (Δ={fps_diff:+5.2f} FPS) | Delay: 20k={r20['hop2_qdelay_median_ms']:5.1f}ms vs 70k={r70['hop2_qdelay_median_ms']:5.1f}ms (Δ={delay_diff:+5.1f}ms) | Loss: 20k={r20['loss_pct']:4.1f}% vs 70k={r70['loss_pct']:4.1f}%")

if __name__ == "__main__":
    main()
