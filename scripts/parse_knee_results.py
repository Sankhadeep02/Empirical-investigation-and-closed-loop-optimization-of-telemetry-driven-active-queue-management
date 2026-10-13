#!/usr/bin/env python3
"""
scripts/parse_knee_results.py

Parses the 8 knee-search diagnostic runs:
  - UDP 1900k (20k vs 70k)
  - UDP 2100k (20k vs 70k)
  - UDP 2300k (20k vs 70k)
  - TCP flow (20k vs 70k)

Applies reviewer methodology:
  1. Ignores first 20 seconds (startup transient) to isolate steady-state dynamics.
  2. Uses INT queue delay on Switch 2 bottleneck as the primary physical criterion.
  3. Evaluates queue spread (IQR), packet loss, and video playback separation.
"""

import re
from pathlib import Path
import numpy as np
import pandas as pd

REPO_ROOT = Path("/home/p4/DESiRED")
LOG_DIR = REPO_ROOT / "src/logs/campaign_v2"
OUT_CSV = REPO_ROOT / "results/campaign_v2/knee_search_steady_state.csv"

CONDITIONS = [
    ("UDP 1.9 Mbps", "knee_UDP_1900k"),
    ("UDP 2.1 Mbps", "knee_UDP_2100k"),
    ("UDP 2.3 Mbps", "knee_UDP_2300k"),
    ("TCP Flow",     "knee_TCP_flow"),
]

POLICIES = ["fixed20k", "fixed70k"]

def parse_run(rid):
    dash_file = LOG_DIR / f"dash_{rid}.txt"
    int_file = LOG_DIR / f"log_INT_{rid}.txt"
    iperf_file = LOG_DIR / f"iperf_client_{rid}.log"

    # 1. Parse DASH (ignoring first 20s)
    fps_steady, buf_steady = [], []
    stalls_steady = 0
    if dash_file.exists():
        lines = [l.strip().split(";") for l in dash_file.read_text().splitlines() if l.strip()]
        if lines:
            t0 = int(lines[0][0])
            for parts in lines:
                if len(parts) >= 4:
                    ts = int(parts[0])
                    rel_s = (ts - t0) / 1000.0
                    if rel_s > 20.0: # Steady-state only
                        b = float(parts[1])
                        f = float(parts[2])
                        fps_steady.append(f)
                        buf_steady.append(b)
                        if f == 0.0:
                            stalls_steady += 1

    # 2. Parse INT (ignoring first 20s)
    deq2_steady, q2_steady = [], []
    if int_file.exists():
        lines = [l.strip().split(",") for l in int_file.read_text().splitlines() if l.strip()]
        if lines:
            t0 = int(lines[0][0])
            for parts in lines:
                if len(parts) >= 31:
                    try:
                        ts = int(parts[0])
                        rel_s = (ts - t0) / 1000.0
                        if rel_s > 20.0: # Steady-state only
                            # Hop 2: parts[19] is deq_timedelta (us), parts[18] is enq_qdepth (pkts)
                            deq2_steady.append(int(parts[19]))
                            q2_steady.append(int(parts[18]))
                    except (ValueError, IndexError):
                        pass

    # 3. Parse iperf
    loss_pct = 0.0
    jitter_ms = 0.0
    bitrate_mbps = 0.0
    retransmissions = 0
    if iperf_file.exists():
        c = iperf_file.read_text(errors='ignore')
        m_loss = re.findall(r"\((\d+\.?\d*)%\)\s+receiver", c)
        if m_loss:
            loss_pct = float(m_loss[-1])
        m_jit = re.findall(r"(\d+\.?\d*)\s+ms\s+\d+/\d+", c)
        if m_jit:
            jitter_ms = float(m_jit[-1])
        m_br = re.findall(r"(\d+\.?\d*)\s+Mbits/sec\s+receiver", c)
        if m_br:
            bitrate_mbps = float(m_br[-1])
        m_retr = re.findall(r"(\d+)\s+sender", c)
        if m_retr:
            try:
                retransmissions = int(m_retr[-1])
            except ValueError:
                pass

    deq_ms = [d / 1000.0 for d in deq2_steady]
    iqr_deq = (np.percentile(deq_ms, 75) - np.percentile(deq_ms, 25)) if len(deq_ms) > 1 else 0.0

    return {
        "run_id": rid,
        "n_int_pts": len(deq_ms),
        "qdelay_median_ms": float(np.median(deq_ms)) if deq_ms else 0.0,
        "qdelay_mean_ms": float(np.mean(deq_ms)) if deq_ms else 0.0,
        "qdelay_iqr_ms": float(iqr_deq),
        "qdepth_median_pkts": float(np.median(q2_steady)) if q2_steady else 0.0,
        "loss_pct": loss_pct,
        "retransmissions": retransmissions,
        "jitter_ms": jitter_ms,
        "iperf_mbps": bitrate_mbps,
        "fps_mean": float(np.mean(fps_steady)) if fps_steady else 0.0,
        "stall_pct": float(stalls_steady / len(fps_steady) * 100.0) if fps_steady else 0.0,
        "buf_mean_s": float(np.mean(buf_steady)) if buf_steady else 0.0,
    }

def main():
    rows = []
    print("="*95)
    print("STEADY-STATE KNEE SEARCH RESULTS (>20s to end, N=1 diagnostic per cell)")
    print("="*95)

    for cond_name, prefix in CONDITIONS:
        for pol in POLICIES:
            rid = f"{prefix}_{pol}"
            res = parse_run(rid)
            res["condition"] = cond_name
            res["policy"] = pol
            rows.append(res)

    df = pd.DataFrame(rows)
    df.to_csv(OUT_CSV, index=False)
    
    # Print comparison
    cols_display = [
        "condition", "policy", "qdelay_median_ms", "qdelay_iqr_ms",
        "qdepth_median_pkts", "loss_pct", "fps_mean", "stall_pct", "buf_mean_s"
    ]
    print(df[cols_display].to_string(index=False))

    print("\n" + "="*95)
    print("CONDITION-BY-CONDITION POLICY SEPARATION (20k vs 70k):")
    print("="*95)
    for cond_name, prefix in CONDITIONS:
        sub = df[df["condition"] == cond_name].set_index("policy")
        r20 = sub.loc["fixed20k"]
        r70 = sub.loc["fixed70k"]
        d_qdelay = r70["qdelay_median_ms"] - r20["qdelay_median_ms"]
        d_fps = r20["fps_mean"] - r70["fps_mean"]
        d_loss = r20["loss_pct"] - r70["loss_pct"]
        print(f"\nCondition: {cond_name}")
        print(f"  - Switch 2 Queue Delay: 20k = {r20['qdelay_median_ms']:.1f} ms | 70k = {r70['qdelay_median_ms']:.1f} ms  -->  Δ(70k - 20k) = {d_qdelay:+.1f} ms (IQR: 20k={r20['qdelay_iqr_ms']:.1f}ms, 70k={r70['qdelay_iqr_ms']:.1f}ms)")
        print(f"  - Queue Depth (pkts):   20k = {r20['qdepth_median_pkts']:.1f}      | 70k = {r70['qdepth_median_pkts']:.1f}")
        print(f"  - Packet Loss (%):      20k = {r20['loss_pct']:.1f}%     | 70k = {r70['loss_pct']:.1f}%")
        print(f"  - Video Playback FPS:   20k = {r20['fps_mean']:.2f}     | 70k = {r70['fps_mean']:.2f}     -->  Δ(20k - 70k) = {d_fps:+.2f} FPS")
        print(f"  - Stall Rate (%):       20k = {r20['stall_pct']:.1f}%     | 70k = {r70['stall_pct']:.1f}%")

if __name__ == "__main__":
    main()
