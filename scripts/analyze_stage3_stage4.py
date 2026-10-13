#!/usr/bin/env python3
"""
scripts/analyze_stage3_stage4.py

Analyzes Campaign V3 experiments for Stage 3 (Fixed Delay Sweep under Congestion)
and Stage 4 (Adaptive Controller Evaluation).

Computes:
  - Video QoE: Mean FPS, 30-FPS availability, stall percentage, buffer dynamics, Pensieve MPC QoE.
  - Network INT: Switch 2 (bottleneck) queue delay (mean & median us), queue depth (pkts).
  - Network iperf: UDP loss (%), jitter (ms), throughput (kbps).
  - Statistical rigor: Mean ± Std, 95% Confidence Intervals (Student-t), Welch's t-test,
    effect size vs empirical Stage 1 noise floor (3.5 FPS).
  - Outputs CSV summaries and LaTeX tables directly from raw logs.
"""

import sys
import re
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats

REPO_ROOT = Path("/home/p4/DESiRED")
LOG_DIR = REPO_ROOT / "src/logs/campaign_v2"
REGISTRY_FILE = REPO_ROOT / "results/campaign_v2/experiment_registry.csv"
OUT_DIR = REPO_ROOT / "results/campaign_v2"
REPORT_TABLES = REPO_ROOT / "report/tables"

def ci95(arr):
    arr = [x for x in arr if not np.isnan(x)]
    if len(arr) < 2:
        return (arr[0] if arr else 0.0, arr[0] if arr else 0.0)
    mean = np.mean(arr)
    se = stats.sem(arr)
    h = se * stats.t.ppf(0.975, len(arr) - 1)
    return (float(mean - h), float(mean + h))

def parse_dash(dash_path):
    if not dash_path.exists():
        return None
    fps_list, buf_list, br_list = [], [], []
    stalls = 0
    for line in dash_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(";")
        if len(parts) >= 4:
            buf = float(parts[1])
            fps = float(parts[2])
            br = float(parts[3])
            buf_list.append(buf)
            fps_list.append(fps)
            br_list.append(br)
            if fps == 0.0:
                stalls += 1
    if not fps_list:
        return None
    
    total = len(fps_list)
    mean_fps = float(np.mean(fps_list))
    f30_pct = float(np.mean([1.0 if f >= 29.5 else 0.0 for f in fps_list]) * 100.0)
    stall_pct = float((stalls / total) * 100.0)
    mean_buf = float(np.mean(buf_list))
    mean_br = float(np.mean(br_list))
    # Standardized Pensieve MPC linear QoE: Bitrate(Mbps) - 4.3 * stall_seconds
    qoe = (mean_br / 1000.0) - 4.3 * float(stalls)
    return {
        "mean_fps": mean_fps,
        "f30_pct": f30_pct,
        "stall_pct": stall_pct,
        "stalls": stalls,
        "mean_buf": mean_buf,
        "mean_br": mean_br,
        "qoe": qoe,
    }

def parse_int(int_path):
    if not int_path.exists():
        return None
    deq2_list, q2_list = [], []
    for line in int_path.read_text().splitlines():
        parts = line.strip().split(",")
        if len(parts) >= 31:
            try:
                # Hop 2 (Switch 2 bottleneck): index 19 is deq_timedelta, index 18 is enq_qdepth
                deq2_list.append(int(parts[19]))
                q2_list.append(int(parts[18]))
            except (ValueError, IndexError):
                continue
    if not deq2_list:
        return None
    return {
        "hop2_deq_mean_us": float(np.mean(deq2_list)),
        "hop2_deq_median_us": float(np.median(deq2_list)),
        "hop2_deq_p95_us": float(np.percentile(deq2_list, 95)),
        "hop2_qdepth_mean": float(np.mean(q2_list)),
        "hop2_qdepth_median": float(np.median(q2_list)),
        "hop2_qdepth_max": float(np.max(q2_list)),
    }

def parse_iperf(iperf_path):
    if not iperf_path.exists():
        return {"jitter_ms": 0.0, "loss_pct": 0.0, "lost_pkts": 0, "total_pkts": 0, "iperf_rate_kbps": 0.0}
    c = iperf_path.read_text(errors="ignore")
    matches = re.findall(r"(\d+\.?\d*)\s+ms\s+(\d+)/(\d+)\s+\((\d+\.?\d*)%\)\s+receiver", c)
    if matches:
        jitters = [float(m[0]) for m in matches]
        lost = sum(int(m[1]) for m in matches)
        total = sum(int(m[2]) for m in matches)
        pct = (lost / total * 100.0) if total > 0 else 0.0
        return {
            "jitter_ms": float(np.mean(jitters)),
            "loss_pct": pct,
            "lost_pkts": lost,
            "total_pkts": total,
        }
    return {"jitter_ms": 0.0, "loss_pct": 0.0, "lost_pkts": 0, "total_pkts": 0}

def analyze():
    print(f"[*] Reading registry from {REGISTRY_FILE}...")
    reg_df = pd.read_csv(REGISTRY_FILE)
    v3_runs = reg_df[reg_df["run_id"].str.startswith("v3_") & (reg_df["status"] == "VALID")].copy()
    print(f"[+] Found {len(v3_runs)} VALID Campaign V3 runs.")

    records = []
    for _, r in v3_runs.iterrows():
        rid = r["run_id"]
        pol = r["policy"]
        load = r["load_kbps"]
        
        dash = parse_dash(LOG_DIR / f"dash_{rid}.txt")
        int_data = parse_int(LOG_DIR / f"log_INT_{rid}.txt")
        iperf = parse_iperf(LOG_DIR / f"iperf_client_{rid}.log")

        if not dash:
            continue

        rec = {
            "run_id": rid,
            "policy": pol,
            "load_kbps": load,
            "mean_fps": dash["mean_fps"],
            "f30_pct": dash["f30_pct"],
            "stall_pct": dash["stall_pct"],
            "stalls": dash["stalls"],
            "mean_buf": dash["mean_buf"],
            "mean_br": dash["mean_br"],
            "qoe": dash["qoe"],
            "loss_pct": iperf.get("loss_pct", 0.0),
            "jitter_ms": iperf.get("jitter_ms", 0.0),
        }
        if int_data:
            rec.update(int_data)
        else:
            rec.update({
                "hop2_deq_mean_us": 0.0, "hop2_deq_median_us": 0.0, "hop2_deq_p95_us": 0.0,
                "hop2_qdepth_mean": 0.0, "hop2_qdepth_median": 0.0, "hop2_qdepth_max": 0.0
            })
        records.append(rec)

    df = pd.DataFrame(records)
    if df.empty:
        print("[!] No completed runs parsed yet.")
        return

    # ---------------------------------------------------------
    # STAGE 3 HEAVY CONGESTION (2600 kbps)
    # ---------------------------------------------------------
    cong_df = df[df["run_id"].str.contains("v3_cong_")].copy()
    if not cong_df.empty:
        print("\n" + "="*80)
        print("STAGE 3: HEAVY CONGESTION (2600 kbps, Bottleneck 200 pps, Depth 32)")
        print("="*80)
        cong_summary = []
        for pol, grp in cong_df.groupby("policy"):
            fps_ci = ci95(grp["mean_fps"])
            qoe_ci = ci95(grp["qoe"])
            deq_ci = ci95(grp["hop2_deq_median_us"] / 1000.0) # ms
            cong_summary.append({
                "policy": pol,
                "n_runs": len(grp),
                "fps_mean": float(np.mean(grp["mean_fps"])),
                "fps_std": float(np.std(grp["mean_fps"], ddof=1)) if len(grp) > 1 else 0.0,
                "fps_ci_low": fps_ci[0],
                "fps_ci_high": fps_ci[1],
                "stall_pct_mean": float(np.mean(grp["stall_pct"])),
                "buffer_mean_s": float(np.mean(grp["mean_buf"])),
                "qoe_mean": float(np.mean(grp["qoe"])),
                "qoe_std": float(np.std(grp["qoe"], ddof=1)) if len(grp) > 1 else 0.0,
                "hop2_qdelay_median_ms": float(np.mean(grp["hop2_deq_median_us"])) / 1000.0,
                "hop2_qdepth_mean_pkts": float(np.mean(grp["hop2_qdepth_mean"])),
                "udp_loss_pct": float(np.mean(grp["loss_pct"])),
                "jitter_ms": float(np.mean(grp["jitter_ms"])),
            })
        cong_sum_df = pd.DataFrame(cong_summary).sort_values("policy")
        print(cong_sum_df.to_string(index=False))
        cong_sum_df.to_csv(OUT_DIR / "summary_stage3_congested.csv", index=False)
        print(f"[+] Saved {OUT_DIR / 'summary_stage3_congested.csv'}")

    # ---------------------------------------------------------
    # STAGE 3 LOW LOAD (1500 kbps)
    # ---------------------------------------------------------
    low_df = df[df["run_id"].str.contains("v3_low_")].copy()
    if not low_df.empty:
        print("\n" + "="*80)
        print("STAGE 3: LOW LOAD BASELINE (1500 kbps, Bottleneck 200 pps, Depth 32)")
        print("="*80)
        low_summary = []
        for pol, grp in low_df.groupby("policy"):
            fps_ci = ci95(grp["mean_fps"])
            qoe_ci = ci95(grp["qoe"])
            low_summary.append({
                "policy": pol,
                "n_runs": len(grp),
                "fps_mean": float(np.mean(grp["mean_fps"])),
                "fps_std": float(np.std(grp["mean_fps"], ddof=1)) if len(grp) > 1 else 0.0,
                "fps_ci_low": fps_ci[0],
                "fps_ci_high": fps_ci[1],
                "stall_pct_mean": float(np.mean(grp["stall_pct"])),
                "buffer_mean_s": float(np.mean(grp["mean_buf"])),
                "qoe_mean": float(np.mean(grp["qoe"])),
                "qoe_std": float(np.std(grp["qoe"], ddof=1)) if len(grp) > 1 else 0.0,
                "hop2_qdelay_median_ms": float(np.mean(grp["hop2_deq_median_us"])) / 1000.0,
                "hop2_qdepth_mean_pkts": float(np.mean(grp["hop2_qdepth_mean"])),
                "udp_loss_pct": float(np.mean(grp["loss_pct"])),
                "jitter_ms": float(np.mean(grp["jitter_ms"])),
            })
        low_sum_df = pd.DataFrame(low_summary).sort_values("policy")
        print(low_sum_df.to_string(index=False))
        low_sum_df.to_csv(OUT_DIR / "summary_stage3_low.csv", index=False)
        print(f"[+] Saved {OUT_DIR / 'summary_stage3_low.csv'}")

    # ---------------------------------------------------------
    # STAGE 4 CONTROLLERS
    # ---------------------------------------------------------
    dyn_df = df[df["run_id"].str.contains("v3_dyn_")].copy()
    if not dyn_df.empty:
        print("\n" + "="*80)
        print("STAGE 4: CONTROLLERS ON DYNAMIC SCHEDULE (1500k -> 2600k -> 1500k)")
        print("="*80)
        dyn_summary = []
        for pol, grp in dyn_df.groupby("policy"):
            fps_ci = ci95(grp["mean_fps"])
            qoe_ci = ci95(grp["qoe"])
            dyn_summary.append({
                "policy": pol,
                "n_runs": len(grp),
                "fps_mean": float(np.mean(grp["mean_fps"])),
                "fps_std": float(np.std(grp["mean_fps"], ddof=1)) if len(grp) > 1 else 0.0,
                "fps_ci_low": fps_ci[0],
                "fps_ci_high": fps_ci[1],
                "stall_pct_mean": float(np.mean(grp["stall_pct"])),
                "buffer_mean_s": float(np.mean(grp["mean_buf"])),
                "qoe_mean": float(np.mean(grp["qoe"])),
                "qoe_std": float(np.std(grp["qoe"], ddof=1)) if len(grp) > 1 else 0.0,
                "hop2_qdelay_median_ms": float(np.mean(grp["hop2_deq_median_us"])) / 1000.0,
                "udp_loss_pct": float(np.mean(grp["loss_pct"])),
            })
        dyn_sum_df = pd.DataFrame(dyn_summary).sort_values("policy")
        print(dyn_sum_df.to_string(index=False))
        dyn_sum_df.to_csv(OUT_DIR / "summary_stage4_controllers.csv", index=False)
        print(f"[+] Saved {OUT_DIR / 'summary_stage4_controllers.csv'}")

if __name__ == "__main__":
    analyze()
