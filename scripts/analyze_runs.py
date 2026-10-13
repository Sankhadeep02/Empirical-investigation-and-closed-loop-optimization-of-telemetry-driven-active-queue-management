#!/usr/bin/env python3
"""
scripts/analyze_runs.py

Comprehensive analysis engine for DESiRED experiment evaluation.
Computes duration-weighted QoE, network QoS, INT telemetry, and controller dynamics.
Calculates statistical aggregates (Mean +/- Std, 95% Confidence Intervals),
generates results/run_summary.csv, results/policy_comparison.csv,
and renders publication-grade vector/raster figures.
"""

import sys
import os
import re
import csv
import math
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

REPO_ROOT = Path("/home/p4/DESiRED")
LOG_DIR = REPO_ROOT / "src/logs"
AGENT_LOG_DIR = REPO_ROOT / "local_controller/agent_logs"
RESULTS_DIR = REPO_ROOT / "results"
FIGS_DIR = REPO_ROOT / "figs"

def percentile(vals, p):
    if not vals:
        return 0.0
    s = sorted(vals)
    k = (len(s) - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(s[int(k)])
    d0 = s[int(f)] * (c - k)
    d1 = s[int(c)] * (k - f)
    return float(d0 + d1)

def parse_dash(dash_path, start_cutoff=0.0):
    """
    Parses dash_<run_id>.txt and returns duration-weighted metrics.
    start_cutoff: seconds from start to skip (for post-convergence slice)
    """
    if not dash_path.exists():
        return None
    
    rows = []
    with open(dash_path, 'r', errors='ignore') as f:
        for line in f:
            parts = line.strip().split(";")
            if len(parts) >= 4:
                try:
                    ts = int(parts[0]) / 1000.0
                    buf = float(parts[1])
                    fps = float(parts[2])
                    br = float(parts[3])
                    rows.append((ts, buf, fps, br))
                except ValueError:
                    continue

    if len(rows) < 2:
        return None

    t0 = rows[0][0]
    
    # Filter by cutoff if requested
    if start_cutoff > 0:
        filtered = [r for r in rows if (r[0] - t0) >= start_cutoff]
        if len(filtered) >= 2:
            rows = filtered
            t0 = rows[0][0]
        else:
            return None

    total_duration = rows[-1][0] - rows[0][0]
    if total_duration <= 0:
        return None

    # Compute duration-weighted metrics
    weighted_fps_sum = 0.0
    weighted_br_sum = 0.0
    weighted_buf_sum = 0.0
    time_30_fps = 0.0
    time_24_fps = 0.0
    time_18_fps = 0.0
    time_0_fps = 0.0
    time_low_buf = 0.0
    min_buf = float('inf')
    max_gap = 0.0

    buffers = []
    fps_list = []

    for i in range(len(rows) - 1):
        dt = rows[i+1][0] - rows[i][0]
        if dt > max_gap:
            max_gap = dt
        # Clamp runaway gaps if any, but maintain weighting
        dt_eff = min(dt, 10.0)
        
        b = rows[i][1]
        fps = rows[i][2]
        br = rows[i][3]

        buffers.append(b)
        fps_list.append(fps)
        if b < min_buf:
            min_buf = b

        weighted_fps_sum += fps * dt_eff
        weighted_br_sum += br * dt_eff
        weighted_buf_sum += b * dt_eff

        if fps >= 30:
            time_30_fps += dt_eff
        elif fps >= 24:
            time_24_fps += dt_eff
        elif fps >= 18:
            time_18_fps += dt_eff
        elif fps == 0:
            time_0_fps += dt_eff

        if b < 3.0:
            time_low_buf += dt_eff

    eff_total_time = sum(min(rows[i+1][0] - rows[i][0], 10.0) for i in range(len(rows)-1))
    if eff_total_time <= 0:
        eff_total_time = total_duration

    return {
        "duration_s": total_duration,
        "sample_count": len(rows),
        "mean_fps": weighted_fps_sum / eff_total_time,
        "median_fps": percentile(fps_list, 0.5),
        "mean_bitrate_kbps": weighted_br_sum / eff_total_time,
        "mean_buffer_s": weighted_buf_sum / eff_total_time,
        "median_buffer_s": percentile(buffers, 0.5),
        "min_buffer_s": min_buf if min_buf != float('inf') else 0.0,
        "frac_30_fps": (time_30_fps / eff_total_time) * 100.0,
        "frac_24_fps": (time_24_fps / eff_total_time) * 100.0,
        "frac_18_fps": (time_18_fps / eff_total_time) * 100.0,
        "frac_0_fps": (time_0_fps / eff_total_time) * 100.0,
        "frac_low_buffer": (time_low_buf / eff_total_time) * 100.0,
        "max_dash_gap_s": max_gap
    }

def parse_iperf(iperf_path):
    if not iperf_path.exists():
        return None
    content = iperf_path.read_text(errors='ignore')
    
    # Look for receiver line: [ ID] Interval Transfer Bitrate Jitter Lost/Total Datagrams
    # e.g.: [  5]   0.00-700.01 sec  41.7 MBytes   499 Kbits/sec  2.286 ms  7/4631 (0.15%)  receiver
    recv_match = re.search(r'\[\s*\d+\]\s+0\.00-\d+\.\d+\s+sec\s+(\d+\.?\d*)\s+MBytes\s+(\d+\.?\d*)\s+(?:Kbits|Mbits)/sec\s+(\d+\.?\d*)\s+ms\s+(\d+)/(\d+)\s+\((\d+\.?\d*)%\)\s+receiver', content)
    if recv_match:
        transfer_mb = float(recv_match.group(1))
        rate_val = float(recv_match.group(2))
        # If rate was reported in Mbits, convert to kbits
        if "Mbits/sec" in recv_match.group(0):
            rate_kbps = rate_val * 1000.0
        else:
            rate_kbps = rate_val
        jitter_ms = float(recv_match.group(3))
        lost_pkts = int(recv_match.group(4))
        total_pkts = int(recv_match.group(5))
        loss_pct = float(recv_match.group(6))
        return {
            "transfer_mbytes": transfer_mb,
            "iperf_rate_kbps": rate_kbps,
            "jitter_ms": jitter_ms,
            "lost_pkts": lost_pkts,
            "total_pkts": total_pkts,
            "loss_pct": loss_pct
        }
    
    # Fallback to general patterns if line formatting differs slightly
    return None

def parse_int_telemetry(int_path):
    if not int_path.exists():
        return None
    
    q_enq1, q_enq2, q_enq3 = [], [], []
    q_deq1, q_deq2, q_deq3 = [], [], []
    deq_delta1, deq_delta2, deq_delta3 = [], [], []

    count = 0
    with open(int_path, 'r', errors='ignore') as f:
        for line in f:
            parts = line.strip().split(",")
            if len(parts) >= 31:
                count += 1
                try:
                    # Switch 3 (hop 3)
                    q_enq3.append(int(parts[7]))
                    q_deq3.append(int(parts[9]))
                    deq_delta3.append(int(parts[8]))
                    # Switch 2 (hop 2)
                    q_enq2.append(int(parts[17]))
                    q_deq2.append(int(parts[19]))
                    deq_delta2.append(int(parts[18]))
                    # Switch 1 (hop 1)
                    q_enq1.append(int(parts[27]))
                    q_deq1.append(int(parts[29]))
                    deq_delta1.append(int(parts[28]))
                except (ValueError, IndexError):
                    continue

    if count == 0:
        return None

    return {
        "int_probes_count": count,
        "hop1_enq_qdepth_median": percentile(q_enq1, 0.5),
        "hop1_enq_qdepth_p95": percentile(q_enq1, 0.95),
        "hop2_enq_qdepth_median": percentile(q_enq2, 0.5),
        "hop2_enq_qdepth_p95": percentile(q_enq2, 0.95),
        "hop3_enq_qdepth_median": percentile(q_enq3, 0.5),
        "hop3_enq_qdepth_p95": percentile(q_enq3, 0.95),
        "hop3_deq_timedelta_mean_us": np.mean(deq_delta3) if deq_delta3 else 0.0,
        "total_deq_timedelta_mean_us": (np.mean(deq_delta1) + np.mean(deq_delta2) + np.mean(deq_delta3)) if deq_delta1 else 0.0
    }

def parse_controller_dynamics(run_id):
    act_path = AGENT_LOG_DIR / f"action_history_{run_id}.csv"
    delay_path = AGENT_LOG_DIR / f"sw1_target_delay_history_{run_id}.csv"
    qval_path = AGENT_LOG_DIR / f"q-values_history_{run_id}.csv"

    res = {
        "actions_total": 0,
        "action_0_count": 0,
        "action_1_count": 0,
        "action_2_count": 0,
        "target_delay_initial": 50000,
        "target_delay_final": 50000,
        "target_delay_mean": 50000.0,
        "clamped_at_min_count": 0
    }

    if act_path.exists():
        actions = []
        with open(act_path, 'r', errors='ignore') as f:
            for l in f:
                if l.strip():
                    try:
                        actions.append(int(l.strip()))
                    except ValueError:
                        pass
        res["actions_total"] = len(actions)
        res["action_0_count"] = actions.count(0)
        res["action_1_count"] = actions.count(1)
        res["action_2_count"] = actions.count(2)

    if delay_path.exists():
        delays = []
        with open(delay_path, 'r', errors='ignore') as f:
            for l in f:
                if l.strip():
                    try:
                        delays.append(int(l.strip()))
                    except ValueError:
                        pass
        if delays:
            res["target_delay_initial"] = delays[0]
            res["target_delay_final"] = delays[-1]
            res["target_delay_mean"] = float(np.mean(delays))
            res["clamped_at_min_count"] = delays.count(20000)

    return res

def analyze_all_runs():
    registry_path = RESULTS_DIR / "experiment_registry.csv"
    if not registry_path.exists():
        print(f"Registry not found: {registry_path}")
        return

    runs = []
    with open(registry_path, 'r', newline='') as f:
        reader = csv.DictReader(f)
        for r in reader:
            if r['status'] == "VALID" or r['status'] == "complete":
                runs.append(r)

    print(f"[*] Found {len(runs)} valid/complete runs to analyze.")

    summary_rows = []

    for r in runs:
        run_id = r['run_id']
        policy = r['policy']
        dash_path = LOG_DIR / f"dash_{run_id}.txt"
        iperf_path = LOG_DIR / f"iperf_client_{run_id}.log"
        int_path = LOG_DIR / f"log_INT_{run_id}.txt"

        dash_res = parse_dash(dash_path)
        iperf_res = parse_iperf(iperf_path)
        int_res = parse_int_telemetry(int_path)
        ctrl_res = parse_controller_dynamics(run_id)

        if not dash_res or not iperf_res:
            print(f"Skipping {run_id}: incomplete logs.")
            continue

        entry = {
            "run_id": run_id,
            "policy": policy,
            "load_kbps": int(r.get("load_kbps", 500)),
            "duration_s": dash_res["duration_s"],
            "dash_samples": dash_res["sample_count"],
            "mean_fps": dash_res["mean_fps"],
            "median_fps": dash_res["median_fps"],
            "mean_bitrate_kbps": dash_res["mean_bitrate_kbps"],
            "mean_buffer_s": dash_res["mean_buffer_s"],
            "median_buffer_s": dash_res["median_buffer_s"],
            "min_buffer_s": dash_res["min_buffer_s"],
            "pct_30_fps": dash_res["frac_30_fps"],
            "pct_24_fps": dash_res["frac_24_fps"],
            "pct_18_fps": dash_res["frac_18_fps"],
            "pct_0_fps": dash_res["frac_0_fps"],
            "pct_low_buffer": dash_res["frac_low_buffer"],
            "iperf_rate_kbps": iperf_res["iperf_rate_kbps"],
            "loss_pct": iperf_res["loss_pct"],
            "jitter_ms": iperf_res["jitter_ms"],
            "int_probes": int_res["int_probes_count"] if int_res else 0,
            "hop3_enq_qdepth_p95": int_res["hop3_enq_qdepth_p95"] if int_res else 0,
            "actions_total": ctrl_res["actions_total"],
            "actions_decrease": ctrl_res["action_1_count"],
            "actions_increase": ctrl_res["action_0_count"],
            "actions_hold": ctrl_res["action_2_count"],
            "target_delay_initial": ctrl_res["target_delay_initial"],
            "target_delay_final": ctrl_res["target_delay_final"],
            "target_delay_mean": ctrl_res["target_delay_mean"],
        }
        summary_rows.append(entry)

        # For RL inference runs, also calculate the post-convergence slice (after t >= 60s)
        if policy in ["RL-inference", "infer"]:
            dash_post = parse_dash(dash_path, start_cutoff=60.0)
            if dash_post:
                entry_post = dict(entry)
                entry_post["run_id"] = f"{run_id}_post"
                entry_post["policy"] = "RL-converged"
                entry_post["duration_s"] = dash_post["duration_s"]
                entry_post["dash_samples"] = dash_post["sample_count"]
                entry_post["mean_fps"] = dash_post["mean_fps"]
                entry_post["median_fps"] = dash_post["median_fps"]
                entry_post["mean_bitrate_kbps"] = dash_post["mean_bitrate_kbps"]
                entry_post["mean_buffer_s"] = dash_post["mean_buffer_s"]
                entry_post["median_buffer_s"] = dash_post["median_buffer_s"]
                entry_post["min_buffer_s"] = dash_post["min_buffer_s"]
                entry_post["pct_30_fps"] = dash_post["frac_30_fps"]
                entry_post["pct_24_fps"] = dash_post["frac_24_fps"]
                entry_post["pct_18_fps"] = dash_post["frac_18_fps"]
                entry_post["pct_0_fps"] = dash_post["frac_0_fps"]
                entry_post["pct_low_buffer"] = dash_post["frac_low_buffer"]
                summary_rows.append(entry_post)

    df_summary = pd.DataFrame(summary_rows)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    summary_csv = RESULTS_DIR / "run_summary.csv"
    df_summary.to_csv(summary_csv, index=False)
    print(f"[+] Saved per-run summary table to {summary_csv}")

    # Compute Statistical Aggregates per policy
    compute_policy_aggregates(df_summary)

def compute_policy_aggregates(df):
    metrics = [
        "mean_fps", "pct_30_fps", "pct_0_fps", "mean_buffer_s", 
        "min_buffer_s", "pct_low_buffer", "mean_bitrate_kbps",
        "iperf_rate_kbps", "loss_pct", "jitter_ms"
    ]

    grouped = df.groupby("policy")
    rows = []

    t_values = {1: 12.71, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306}

    for policy_name, group in grouped:
        n = len(group)
        p_row = {"policy": policy_name, "replications": n}
        t_crit = t_values.get(n - 1, 2.0) if n > 1 else 0.0

        for m in metrics:
            vals = group[m].values
            mean_v = float(np.mean(vals))
            std_v = float(np.std(vals, ddof=1)) if n > 1 else 0.0
            ci_v = (t_crit * std_v / math.sqrt(n)) if n > 1 else 0.0
            
            p_row[f"{m}_mean"] = mean_v
            p_row[f"{m}_std"] = std_v
            p_row[f"{m}_ci95"] = ci_v
            p_row[f"{m}_formatted"] = f"{mean_v:.2f} +/- {std_v:.2f} (CI: [{mean_v-ci_v:.2f}, {mean_v+ci_v:.2f}])" if n > 1 else f"{mean_v:.2f}"

        rows.append(p_row)

    df_agg = pd.DataFrame(rows)
    agg_csv = RESULTS_DIR / "policy_comparison.csv"
    df_agg.to_csv(agg_csv, index=False)
    print(f"[+] Saved policy aggregates table to {agg_csv}")

    # Generate Publication Plots
    plot_evaluation_figures(df, df_agg)

def plot_evaluation_figures(df_runs, df_agg):
    FIGS_DIR.mkdir(parents=True, exist_ok=True)
    plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
    
    # 1. QoE FPS and 30 FPS Availability
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    
    policies = df_agg['policy'].tolist()
    fps_means = df_agg['mean_fps_mean'].tolist()
    fps_errs = df_agg['mean_fps_std'].tolist()
    avail_means = df_agg['pct_30_fps_mean'].tolist()
    avail_errs = df_agg['pct_30_fps_std'].tolist()

    x = np.arange(len(policies))
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b']

    ax1.bar(x, fps_means, yerr=fps_errs, capsize=5, color=colors[:len(policies)], alpha=0.85, edgecolor='black')
    ax1.set_xticks(x)
    ax1.set_xticklabels(policies, rotation=20, ha='right', fontsize=11)
    ax1.set_ylabel("Duration-Weighted Mean FPS", fontsize=12)
    ax1.set_title("Video Playback Frame Rate (FPS)", fontsize=13, fontweight='bold')
    ax1.set_ylim(0, 32)
    for i, v in enumerate(fps_means):
        ax1.text(i, v + 1.0, f"{v:.1f}", ha='center', fontsize=10, fontweight='bold')

    ax2.bar(x, avail_means, yerr=avail_errs, capsize=5, color=colors[:len(policies)], alpha=0.85, edgecolor='black')
    ax2.set_xticks(x)
    ax2.set_xticklabels(policies, rotation=20, ha='right', fontsize=11)
    ax2.set_ylabel("Time at 30 FPS (%)", fontsize=12)
    ax2.set_title("High-Quality Availability (30 FPS)", fontsize=13, fontweight='bold')
    ax2.set_ylim(0, 105)
    for i, v in enumerate(avail_means):
        ax2.text(i, v + 2.0, f"{v:.1f}%", ha='center', fontsize=10, fontweight='bold')

    plt.tight_layout()
    plt.savefig(FIGS_DIR / "qoe_comparison.png", dpi=300)
    plt.close()
    print(f"[+] Saved {FIGS_DIR / 'qoe_comparison.png'}")

    # 2. Buffer Dynamics & Stalls
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    buf_means = df_agg['mean_buffer_s_mean'].tolist()
    buf_errs = df_agg['mean_buffer_s_std'].tolist()
    stall_means = df_agg['pct_0_fps_mean'].tolist()
    stall_errs = df_agg['pct_0_fps_std'].tolist()

    ax1.bar(x, buf_means, yerr=buf_errs, capsize=5, color=colors[:len(policies)], alpha=0.85, edgecolor='black')
    ax1.set_xticks(x)
    ax1.set_xticklabels(policies, rotation=20, ha='right', fontsize=11)
    ax1.set_ylabel("Mean Video Buffer (seconds)", fontsize=12)
    ax1.set_title("Video Playback Buffer Level", fontsize=13, fontweight='bold')
    for i, v in enumerate(buf_means):
        ax1.text(i, v + 0.8, f"{v:.1f}s", ha='center', fontsize=10, fontweight='bold')

    ax2.bar(x, stall_means, yerr=stall_errs, capsize=5, color=colors[:len(policies)], alpha=0.85, edgecolor='black')
    ax2.set_xticks(x)
    ax2.set_xticklabels(policies, rotation=20, ha='right', fontsize=11)
    ax2.set_ylabel("Rebuffer / Stall Time (%)", fontsize=12)
    ax2.set_title("Rebuffer Ratio (0 FPS)", fontsize=13, fontweight='bold')
    for i, v in enumerate(stall_means):
        ax2.text(i, v + 0.5, f"{v:.2f}%", ha='center', fontsize=10, fontweight='bold')

    plt.tight_layout()
    plt.savefig(FIGS_DIR / "buffer_dynamics.png", dpi=300)
    plt.close()
    print(f"[+] Saved {FIGS_DIR / 'buffer_dynamics.png'}")

    # 3. Network Loss and Jitter
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    loss_means = df_agg['loss_pct_mean'].tolist()
    loss_errs = df_agg['loss_pct_std'].tolist()
    jitter_means = df_agg['jitter_ms_mean'].tolist()
    jitter_errs = df_agg['jitter_ms_std'].tolist()

    ax1.bar(x, loss_means, yerr=loss_errs, capsize=5, color=colors[:len(policies)], alpha=0.85, edgecolor='black')
    ax1.set_xticks(x)
    ax1.set_xticklabels(policies, rotation=20, ha='right', fontsize=11)
    ax1.set_ylabel("Datagram Loss (%)", fontsize=12)
    ax1.set_title("UDP Network Datagram Loss", fontsize=13, fontweight='bold')
    for i, v in enumerate(loss_means):
        ax1.text(i, v + 0.05, f"{v:.2f}%", ha='center', fontsize=10, fontweight='bold')

    ax2.bar(x, jitter_means, yerr=jitter_errs, capsize=5, color=colors[:len(policies)], alpha=0.85, edgecolor='black')
    ax2.set_xticks(x)
    ax2.set_xticklabels(policies, rotation=20, ha='right', fontsize=11)
    ax2.set_ylabel("Receiver Jitter (ms)", fontsize=12)
    ax2.set_title("UDP Receiver Delay Jitter", fontsize=13, fontweight='bold')
    for i, v in enumerate(jitter_means):
        ax2.text(i, v + 1.0, f"{v:.1f}ms", ha='center', fontsize=10, fontweight='bold')

    plt.tight_layout()
    plt.savefig(FIGS_DIR / "network_performance.png", dpi=300)
    plt.close()
    print(f"[+] Saved {FIGS_DIR / 'network_performance.png'}")

def main():
    analyze_all_runs()

if __name__ == "__main__":
    main()
