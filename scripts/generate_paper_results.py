#!/usr/bin/env python3
"""
scripts/generate_paper_results.py

DESiRED – Publication-grade analysis, aggregation and figure generator.
Runs on whatever data is available in experiment_registry.csv (VALID or complete).
Also ingests legacy runs (infer_socket_load_4, fixed20k_load_1) directly.

Outputs:
  results/run_summary.csv          – per-run metrics table
  results/policy_comparison.csv    – mean ± SD ± 95% CI per policy
  results/paper_results.md         – publishable results summary (Markdown)
  figs/qoe_comparison.png          – FPS & 30-FPS availability bar chart
  figs/buffer_dynamics.png         – buffer level & stall time bar chart
  figs/network_performance.png     – UDP loss & jitter bar chart
  figs/target_delay_trajectory.png – target delay over time (RL/rule runs)
"""

import sys, os, re, csv, math
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

REPO_ROOT    = Path("/home/p4/DESiRED")
LOG_DIR      = REPO_ROOT / "src/logs"
AGENT_DIR    = REPO_ROOT / "local_controller/agent_logs"
RESULTS_DIR  = REPO_ROOT / "results"
FIGS_DIR     = REPO_ROOT / "figs"

# ── t-distribution critical values (two-tailed, 95%) ──────────────────────────
T_CRIT = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776,
           5: 2.571,  6: 2.447, 7: 2.365, 8: 2.306,
           9: 2.262, 10: 2.228}

def t_crit(df_):          # df_ = degrees of freedom
    return T_CRIT.get(df_, 2.0)

def ci95(vals):
    n = len(vals)
    if n < 2: return 0.0
    return t_crit(n-1) * np.std(vals, ddof=1) / math.sqrt(n)

def percentile(vals, p):
    if not vals: return 0.0
    s = sorted(vals); k = (len(s)-1)*p
    f,c = math.floor(k), math.ceil(k)
    if f==c: return float(s[int(k)])
    return float(s[int(f)]*(c-k) + s[int(c)]*(k-f))

# ── Log parsers ───────────────────────────────────────────────────────────────
def parse_dash(path):
    path = Path(path)
    if not path.exists(): return None
    rows = []
    for line in path.read_text(errors='ignore').splitlines():
        parts = line.strip().split(";")
        if len(parts) >= 4:
            try:
                ts = int(parts[0])/1000.0
                buf = float(parts[1]); fps = float(parts[2]); br = float(parts[3])
                rows.append((ts, buf, fps, br))
            except ValueError: continue
    if len(rows) < 2: return None
    rows.sort(key=lambda r: r[0])
    total = rows[-1][0] - rows[0][0]
    if total <= 0: return None

    wfps=wbr=wbuf=t30=t24=t18=t0=tlow=0.0
    bufs, fpsl = [], []
    min_buf = float('inf')
    max_gap = 0.0
    teff = 0.0

    for i in range(len(rows)-1):
        dt = rows[i+1][0]-rows[i][0]
        max_gap = max(max_gap, dt)
        dte = min(dt, 10.0)
        teff += dte
        b,fps,br = rows[i][1], rows[i][2], rows[i][3]
        bufs.append(b); fpsl.append(fps)
        min_buf = min(min_buf, b)
        wfps+=fps*dte; wbr+=br*dte; wbuf+=b*dte
        if fps>=30: t30+=dte
        elif fps>=24: t24+=dte
        elif fps>=18: t18+=dte
        elif fps==0: t0+=dte
        if b<3.0: tlow+=dte

    if teff<=0: teff=total
    return dict(
        duration_s=total, sample_count=len(rows),
        mean_fps=wfps/teff, median_fps=percentile(fpsl,0.5),
        mean_bitrate_kbps=wbr/teff,
        mean_buffer_s=wbuf/teff, median_buffer_s=percentile(bufs,0.5),
        min_buffer_s=min_buf if min_buf!=float('inf') else 0.0,
        frac_30_fps=t30/teff*100, frac_24_fps=t24/teff*100,
        frac_18_fps=t18/teff*100, frac_0_fps=t0/teff*100,
        frac_low_buffer=tlow/teff*100, max_dash_gap_s=max_gap
    )

def parse_iperf(path):
    path = Path(path)
    if not path.exists(): return None
    c = path.read_text(errors='ignore')
    m = re.search(
        r'\[\s*\d+\]\s+0\.00-\d+\.\d+\s+sec\s+(\d+\.?\d*)\s+MBytes\s+'
        r'(\d+\.?\d*)\s+(Kbits|Mbits)/sec\s+(\d+\.?\d*)\s+ms\s+'
        r'(\d+)/(\d+)\s+\((\d+\.?\d*)%\)\s+receiver', c)
    if not m: return None
    rate = float(m.group(2)) * (1000 if m.group(3)=="Mbits" else 1)
    return dict(transfer_mbytes=float(m.group(1)),
                iperf_rate_kbps=rate, jitter_ms=float(m.group(4)),
                lost_pkts=int(m.group(5)), total_pkts=int(m.group(6)),
                loss_pct=float(m.group(7)))

def parse_int(path):
    path = Path(path)
    if not path.exists(): return None
    q1e,q2e,q3e=[],[],[]
    d1,d2,d3=[],[],[]
    cnt=0
    for line in path.read_text(errors='ignore').splitlines():
        p=line.strip().split(",")
        if len(p)>=31:
            try:
                q3e.append(int(p[7])); d3.append(int(p[8]))
                q2e.append(int(p[17])); d2.append(int(p[18]))
                q1e.append(int(p[27])); d1.append(int(p[28]))
                cnt+=1
            except (ValueError,IndexError): pass
    if cnt==0: return None
    return dict(
        int_probes_count=cnt,
        hop1_enq_q_median=percentile(q1e,0.5), hop1_enq_q_p95=percentile(q1e,0.95),
        hop2_enq_q_median=percentile(q2e,0.5), hop2_enq_q_p95=percentile(q2e,0.95),
        hop3_enq_q_median=percentile(q3e,0.5), hop3_enq_q_p95=percentile(q3e,0.95),
        hop3_deq_delta_mean_us=float(np.mean(d3)) if d3 else 0.0,
        total_deq_delta_mean_us=float(np.mean(d1)+np.mean(d2)+np.mean(d3)) if d1 else 0.0
    )

def parse_ctrl(run_id):
    ap = AGENT_DIR/f"action_history_{run_id}.csv"
    dp = AGENT_DIR/f"sw1_target_delay_history_{run_id}.csv"
    res=dict(actions_total=0,action_0=0,action_1=0,action_2=0,
             delay_init=50000,delay_final=50000,delay_mean=50000.0,clamped_at_min=0)
    if ap.exists():
        acts=[]
        for l in ap.read_text(errors='ignore').splitlines():
            try: acts.append(int(l.strip()))
            except ValueError: pass
        res.update(actions_total=len(acts),action_0=acts.count(0),
                   action_1=acts.count(1),action_2=acts.count(2))
    if dp.exists():
        ds=[]
        for l in dp.read_text(errors='ignore').splitlines():
            try: ds.append(int(l.strip()))
            except ValueError: pass
        if ds:
            res.update(delay_init=ds[0],delay_final=ds[-1],
                       delay_mean=float(np.mean(ds)),clamped_at_min=ds.count(20000))
    return res

# ── Policy name mapping (canonical) ──────────────────────────────────────────
POLICY_LABEL = {
    "fixed-20k": "Fixed-20k","fixed20k": "Fixed-20k",
    "fixed-30k": "Fixed-30k","fixed30k": "Fixed-30k",
    "fixed-40k": "Fixed-40k","fixed40k": "Fixed-40k",
    "fixed-50k": "Fixed-50k","fixed50k": "Fixed-50k",
    "RL-inference": "RL-DDQN","infer": "RL-DDQN",
    "rule": "Rule-Based","rule-based": "Rule-Based",
}

POLICY_ORDER = ["Fixed-20k","Fixed-30k","Fixed-40k","Fixed-50k","Rule-Based","RL-DDQN"]
COLORS = {
    "Fixed-20k":  "#2176AE",
    "Fixed-30k":  "#57B8FF",
    "Fixed-40k":  "#3DDC84",
    "Fixed-50k":  "#FF8811",
    "Rule-Based": "#C1292E",
    "RL-DDQN":    "#7B2D8B",
}

# ── Main analysis ─────────────────────────────────────────────────────────────
def analyze():
    RESULTS_DIR.mkdir(parents=True,exist_ok=True)
    FIGS_DIR.mkdir(parents=True,exist_ok=True)

    reg = RESULTS_DIR/"experiment_registry.csv"
    if not reg.exists():
        print("No registry found."); return

    records=[]
    with open(reg,'r') as f:
        reader=csv.DictReader(f)
        for r in reader:
            if r['status'].lower() in ('valid','complete','valid '):
                records.append(r)

    print(f"[*] {len(records)} valid/complete runs found in registry.")

    rows=[]
    for r in records:
        rid=r['run_id']
        pol=POLICY_LABEL.get(r['policy'],r['policy'])

        dash=parse_dash(LOG_DIR/f"dash_{rid}.txt")
        iperf=parse_iperf(LOG_DIR/f"iperf_client_{rid}.log")
        int_=parse_int(LOG_DIR/f"log_INT_{rid}.txt")
        ctrl=parse_ctrl(rid)

        if not dash or not iperf:
            print(f"  [skip] {rid}: incomplete logs (dash={dash is not None}, iperf={iperf is not None})")
            continue

        entry=dict(
            run_id=rid, policy=pol,
            load_kbps=int(r.get('load_kbps',500)),
            duration_s=dash['duration_s'], dash_samples=dash['sample_count'],
            mean_fps=dash['mean_fps'], median_fps=dash['median_fps'],
            mean_bitrate_kbps=dash['mean_bitrate_kbps'],
            mean_buffer_s=dash['mean_buffer_s'], median_buffer_s=dash['median_buffer_s'],
            min_buffer_s=dash['min_buffer_s'],
            pct_30_fps=dash['frac_30_fps'], pct_24_fps=dash['frac_24_fps'],
            pct_18_fps=dash['frac_18_fps'], pct_0_fps=dash['frac_0_fps'],
            pct_low_buffer=dash['frac_low_buffer'],
            iperf_rate_kbps=iperf['iperf_rate_kbps'],
            loss_pct=iperf['loss_pct'], jitter_ms=iperf['jitter_ms'],
            int_probes=int_['int_probes_count'] if int_ else 0,
            hop3_enq_q_p95=int_['hop3_enq_q_p95'] if int_ else 0,
            total_deq_us=int_['total_deq_delta_mean_us'] if int_ else 0,
            actions_total=ctrl['actions_total'],
            action_0=ctrl['action_0'], action_1=ctrl['action_1'], action_2=ctrl['action_2'],
            delay_init=ctrl['delay_init'], delay_final=ctrl['delay_final'],
            delay_mean=ctrl['delay_mean'],
        )
        rows.append(entry)
        print(f"  [ok] {rid} | {pol} | FPS={entry['mean_fps']:.1f} | buf={entry['mean_buffer_s']:.1f}s | loss={entry['loss_pct']:.2f}%")

    if not rows:
        print("[!] No complete runs to analyze yet — re-run after experiments finish."); return

    df = pd.DataFrame(rows)
    df.to_csv(RESULTS_DIR/"run_summary.csv", index=False)
    print(f"\n[+] Saved run_summary.csv ({len(df)} runs)")

    # ── Policy aggregation ─────────────────────────────────────────────────────
    METRICS = ["mean_fps","pct_30_fps","pct_0_fps","mean_buffer_s","min_buffer_s",
               "pct_low_buffer","mean_bitrate_kbps","iperf_rate_kbps","loss_pct","jitter_ms"]

    agg_rows=[]
    for pol in POLICY_ORDER:
        sub=df[df['policy']==pol]
        if sub.empty: continue
        n=len(sub)
        row={"policy":pol,"replications":n}
        for m in METRICS:
            vals=sub[m].values
            mn=float(np.mean(vals))
            sd=float(np.std(vals,ddof=1)) if n>1 else 0.0
            ci=ci95(vals) if n>1 else 0.0
            row[f"{m}_mean"]=mn; row[f"{m}_sd"]=sd; row[f"{m}_ci95"]=ci
            row[f"{m}_fmt"]=f"{mn:.2f} ± {sd:.2f} (95% CI ±{ci:.2f})" if n>1 else f"{mn:.2f}"
        agg_rows.append(row)

    df_agg=pd.DataFrame(agg_rows)
    df_agg.to_csv(RESULTS_DIR/"policy_comparison.csv",index=False)
    print(f"[+] Saved policy_comparison.csv")

    # ── Figures ────────────────────────────────────────────────────────────────
    pols=[r['policy'] for r in agg_rows]
    xcol=np.arange(len(pols))
    bar_colors=[COLORS.get(p,"#999999") for p in pols]

    def bar_plot(ax, means, errs, ylabel, title, fmt_str="{:.1f}"):
        bars=ax.bar(xcol, means, yerr=errs, capsize=6,
                    color=bar_colors, alpha=0.88, edgecolor='#222222', linewidth=0.8)
        ax.set_xticks(xcol)
        ax.set_xticklabels(pols, rotation=22, ha='right', fontsize=10)
        ax.set_ylabel(ylabel, fontsize=11)
        ax.set_title(title, fontsize=12, fontweight='bold', pad=8)
        for i,(v,e) in enumerate(zip(means,errs)):
            ax.text(i, v+e+abs(v)*0.02+0.3, fmt_str.format(v),
                    ha='center', fontsize=9, fontweight='bold')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

    # Fig 1: QoE – FPS
    fig,(ax1,ax2)=plt.subplots(1,2,figsize=(13,5.5))
    fig.suptitle("DESiRED: Video QoE Comparison Across Control Policies",
                 fontsize=13, fontweight='bold', y=1.01)
    bar_plot(ax1,
             [r['mean_fps_mean'] for r in agg_rows],
             [r['mean_fps_ci95'] for r in agg_rows],
             "Duration-Weighted Mean FPS","(a) Mean Video Playback FPS","{:.1f} fps")
    ax1.set_ylim(0,33)
    bar_plot(ax2,
             [r['pct_30_fps_mean'] for r in agg_rows],
             [r['pct_30_fps_ci95'] for r in agg_rows],
             "Time at 30 FPS (%)","(b) High-Quality Availability","{:.1f}%")
    ax2.set_ylim(0,108)
    plt.tight_layout()
    plt.savefig(FIGS_DIR/"qoe_comparison.png",dpi=300,bbox_inches='tight')
    plt.close(); print("[+] Saved figs/qoe_comparison.png")

    # Fig 2: Buffer & Stalls
    fig,(ax1,ax2)=plt.subplots(1,2,figsize=(13,5.5))
    fig.suptitle("DESiRED: Buffer Dynamics & Rebuffer Ratio",
                 fontsize=13, fontweight='bold', y=1.01)
    bar_plot(ax1,
             [r['mean_buffer_s_mean'] for r in agg_rows],
             [r['mean_buffer_s_ci95'] for r in agg_rows],
             "Mean Video Buffer (s)","(a) Mean Buffer Level","{:.1f}s")
    bar_plot(ax2,
             [r['pct_0_fps_mean'] for r in agg_rows],
             [r['pct_0_fps_ci95'] for r in agg_rows],
             "Rebuffer / Stall Time (%)","(b) Rebuffer Ratio (FPS=0)","{:.2f}%")
    plt.tight_layout()
    plt.savefig(FIGS_DIR/"buffer_dynamics.png",dpi=300,bbox_inches='tight')
    plt.close(); print("[+] Saved figs/buffer_dynamics.png")

    # Fig 3: Network
    fig,(ax1,ax2)=plt.subplots(1,2,figsize=(13,5.5))
    fig.suptitle("DESiRED: Network Loss & Jitter Under Competing Load",
                 fontsize=13, fontweight='bold', y=1.01)
    bar_plot(ax1,
             [r['loss_pct_mean'] for r in agg_rows],
             [r['loss_pct_ci95'] for r in agg_rows],
             "UDP Datagram Loss (%)","(a) Packet Loss Rate","{:.2f}%")
    bar_plot(ax2,
             [r['jitter_ms_mean'] for r in agg_rows],
             [r['jitter_ms_ci95'] for r in agg_rows],
             "Receiver Jitter (ms)","(b) UDP Delay Jitter","{:.1f} ms")
    plt.tight_layout()
    plt.savefig(FIGS_DIR/"network_performance.png",dpi=300,bbox_inches='tight')
    plt.close(); print("[+] Saved figs/network_performance.png")

    # Fig 4: Target delay trajectory for RL/rule runs
    ctrl_runs=df[df['policy'].isin(["RL-DDQN","Rule-Based"])]['run_id'].tolist()
    if ctrl_runs:
        fig,ax=plt.subplots(figsize=(12,5))
        for rid in ctrl_runs:
            dp=AGENT_DIR/f"sw1_target_delay_history_{rid}.csv"
            if not dp.exists(): continue
            delays=[]
            for l in dp.read_text(errors='ignore').splitlines():
                try: delays.append(int(l.strip()))
                except ValueError: pass
            if delays:
                pol=df[df['run_id']==rid]['policy'].values[0]
                c=COLORS.get(pol,"#999")
                t=[i*10 for i in range(len(delays))]
                ax.plot(t,np.array(delays)/1000.0,color=c,alpha=0.75,linewidth=1.4,
                        label=f"{pol} ({rid})")
        ax.set_xlabel("Elapsed Time (s)", fontsize=11)
        ax.set_ylabel("Target Delay (ms)", fontsize=11)
        ax.set_title("DESiRED: Controller Target Delay Trajectory",
                     fontsize=12, fontweight='bold')
        ax.set_ylim(15,75); ax.set_xlim(0)
        ax.axhline(20,color='#888',ls='--',lw=0.8,label='Min (20ms)')
        ax.axhline(70,color='#888',ls=':',lw=0.8,label='Max (70ms)')
        ax.legend(fontsize=8, ncol=2, loc='upper right')
        ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
        plt.tight_layout()
        plt.savefig(FIGS_DIR/"target_delay_trajectory.png",dpi=300,bbox_inches='tight')
        plt.close(); print("[+] Saved figs/target_delay_trajectory.png")

    # ── Paper-results report ───────────────────────────────────────────────────
    write_paper_report(df, df_agg, agg_rows)

def write_paper_report(df, df_agg, agg_rows):
    lines=[]
    lines.append("# DESiRED Evaluation Results\n")
    lines.append(f"*Generated automatically from {len(df)} experiment runs.*\n")
    lines.append("> All metrics are duration-weighted integrals (see experiment_plan.md §3).\n")

    lines.append("\n## 1. Per-Run Raw Summary\n")
    lines.append("| Run ID | Policy | Mean FPS | 30-FPS% | Stall% | Buf(s) | Loss% | Jitter(ms) | INT probes |")
    lines.append("|--------|--------|----------|---------|--------|--------|-------|-----------|------------|")
    for _,r in df.iterrows():
        lines.append(f"| {r.run_id} | {r.policy} | {r.mean_fps:.1f} | {r.pct_30_fps:.1f} | "
                     f"{r.pct_0_fps:.2f} | {r.mean_buffer_s:.1f} | {r.loss_pct:.2f} | "
                     f"{r.jitter_ms:.1f} | {int(r.int_probes)} |")

    lines.append("\n## 2. Policy Aggregate Statistics (Mean ± SD, 95% CI)\n")
    lines.append("| Policy | N | Mean FPS | 30-FPS% | Stall% | Mean Buf (s) | Loss% | Jitter (ms) |")
    lines.append("|--------|---|----------|---------|--------|-------------|-------|-------------|")
    for r in agg_rows:
        lines.append(
            f"| **{r['policy']}** | {r['replications']} "
            f"| {r['mean_fps_fmt']} "
            f"| {r['pct_30_fps_fmt']} "
            f"| {r['pct_0_fps_fmt']} "
            f"| {r['mean_buffer_s_fmt']} "
            f"| {r['loss_pct_fmt']} "
            f"| {r['jitter_ms_fmt']} |"
        )

    lines.append("\n## 3. Key Findings\n")

    # Find best FPS policy
    if agg_rows:
        best_fps = max(agg_rows, key=lambda r: r['mean_fps_mean'])
        best_30  = max(agg_rows, key=lambda r: r['pct_30_fps_mean'])
        best_buf = max(agg_rows, key=lambda r: r['mean_buffer_s_mean'])
        low_loss = min(agg_rows, key=lambda r: r['loss_pct_mean'])
        low_stall= min(agg_rows, key=lambda r: r['pct_0_fps_mean'])

        lines.append(f"- **Highest mean FPS:** {best_fps['policy']} ({best_fps['mean_fps_fmt']})")
        lines.append(f"- **Best 30-FPS availability:** {best_30['policy']} ({best_30['pct_30_fps_fmt']})")
        lines.append(f"- **Highest mean video buffer:** {best_buf['policy']} ({best_buf['mean_buffer_s_fmt']} s)")
        lines.append(f"- **Lowest UDP loss:** {low_loss['policy']} ({low_loss['loss_pct_fmt']}%)")
        lines.append(f"- **Lowest rebuffer ratio:** {low_stall['policy']} ({low_stall['pct_0_fps_fmt']}%)")

    lines.append("\n## 4. Controller Dynamics (RL & Rule-Based Runs)\n")
    ctrl_df=df[df['policy'].isin(["RL-DDQN","Rule-Based"])]
    if not ctrl_df.empty:
        lines.append("| Run ID | Policy | Actions | ↑ Inc | ↓ Dec | → Hold | Init Delay | Final Delay |")
        lines.append("|--------|--------|---------|-------|-------|--------|-----------|------------|")
        for _,r in ctrl_df.iterrows():
            lines.append(f"| {r.run_id} | {r.policy} | {int(r.actions_total)} | "
                         f"{int(r.action_0)} | {int(r.action_1)} | {int(r.action_2)} | "
                         f"{int(r.delay_init)} µs | {int(r.delay_final)} µs |")
    else:
        lines.append("*No controller runs completed yet.*\n")

    lines.append("\n## 5. Figures\n")
    lines.append("| Figure | Description |")
    lines.append("|--------|-------------|")
    lines.append("| `figs/qoe_comparison.png` | Mean FPS & 30-FPS availability per policy |")
    lines.append("| `figs/buffer_dynamics.png` | Mean buffer level & stall rate per policy |")
    lines.append("| `figs/network_performance.png` | UDP loss & jitter per policy |")
    lines.append("| `figs/target_delay_trajectory.png` | Target delay over time for RL/rule runs |")

    report = "\n".join(lines) + "\n"
    rpath = RESULTS_DIR/"paper_results.md"
    rpath.write_text(report)
    print(f"[+] Saved results/paper_results.md")

if __name__ == "__main__":
    analyze()
