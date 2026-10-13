#!/usr/bin/env python3
"""
scripts/final_analysis_v2.py
DESiRED - Final Publication Analysis on campaign_v2 dataset.

Reads from:
  src/logs/campaign_v2/           -- DASH, INT, iperf logs
  local_controller/agent_logs/campaign_v2/  -- action/delay histories

Outputs:
  results/run_summary_v2.csv        per-run detailed metrics
  results/policy_comparison_v2.csv  mean±SD±CI per policy
  results/paper_results_v2.md       publication-ready Markdown report
  figs/v2_qoe_fps.png               FPS & 30-FPS availability
  figs/v2_buffer_stall.png          buffer level & stall ratio
  figs/v2_network.png               UDP loss & jitter
  figs/v2_delay_trajectory.png      controller target-delay over time
  figs/v2_int_queue.png             INT queue depth per hop
"""

import sys, re, csv, math
from pathlib import Path
from collections import defaultdict
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.patches import Patch

REPO     = Path("/home/p4/DESiRED")
V2_LOGS  = REPO / "src/logs/campaign_v2"
AGENT_V2 = REPO / "local_controller/agent_logs/campaign_v2"
RESULTS  = REPO / "results"
FIGS     = REPO / "figs"

# ── Policy display names & ordering ──────────────────────────────────────────
POLICY_ORDER  = ["Fixed-20k","Fixed-30k","Fixed-40k","Fixed-50k","Rule-Based","RL-DDQN"]
POL_PREFIX    = {"fixed20k":"Fixed-20k","fixed30k":"Fixed-30k",
                 "fixed40k":"Fixed-40k","fixed50k":"Fixed-50k",
                 "rule":"Rule-Based","infer":"RL-DDQN"}
COLORS = {
    "Fixed-20k":  "#1565C0",
    "Fixed-30k":  "#42A5F5",
    "Fixed-40k":  "#2E7D32",
    "Fixed-50k":  "#F57F17",
    "Rule-Based": "#B71C1C",
    "RL-DDQN":    "#6A1B9A",
}
HATCHES = {
    "Fixed-20k":  "",
    "Fixed-30k":  "//",
    "Fixed-40k":  "..",
    "Fixed-50k":  "xx",
    "Rule-Based": "++",
    "RL-DDQN":    "oo",
}

# ── Statistics helpers ────────────────────────────────────────────────────────
T_CRIT = {1:12.706,2:4.303,3:3.182,4:2.776,5:2.571,6:2.447,7:2.365,8:2.306}

def ci95(vals):
    n = len(vals)
    if n < 2: return 0.0
    t = T_CRIT.get(n-1, 2.0)
    return t * np.std(vals, ddof=1) / math.sqrt(n)

def pct(vals, p):
    if not vals: return 0.0
    s = sorted(vals)
    k = (len(s)-1)*p
    f, c = math.floor(k), math.ceil(k)
    if f == c: return float(s[int(k)])
    return float(s[int(f)]*(c-k) + s[int(c)]*(k-f))

# ── Log parsers ───────────────────────────────────────────────────────────────
def parse_dash(path):
    if not path.exists(): return None
    rows = []
    for line in path.read_text(errors='ignore').splitlines():
        p = line.strip().split(";")
        if len(p) >= 4:
            try: rows.append((int(p[0])/1000., float(p[1]), float(p[2]), float(p[3])))
            except ValueError: pass
    if len(rows) < 10: return None
    rows.sort(key=lambda r: r[0])
    total = rows[-1][0] - rows[0][0]
    if total <= 0: return None

    wfps=wbr=wbuf=t30=t24=t18=t0=tlow=teff=0.
    bufs,fpsl=[],[]
    min_buf = float('inf')
    max_gap = 0.
    for i in range(len(rows)-1):
        dt = rows[i+1][0]-rows[i][0]
        max_gap = max(max_gap, dt)
        dte = min(dt, 10.)
        teff += dte
        b,fps,br = rows[i][1],rows[i][2],rows[i][3]
        bufs.append(b); fpsl.append(fps)
        min_buf = min(min_buf, b)
        wfps+=fps*dte; wbr+=br*dte; wbuf+=b*dte
        if fps>=30: t30+=dte
        elif fps>=24: t24+=dte
        elif fps>=18: t18+=dte
        elif fps==0: t0+=dte
        if b<3.0: tlow+=dte
    if teff<=0: teff=total
    return dict(dur=total, n=len(rows),
                mean_fps=wfps/teff, med_fps=pct(fpsl,0.5),
                mean_br=wbr/teff,
                mean_buf=wbuf/teff, med_buf=pct(bufs,0.5),
                min_buf=min_buf if min_buf!=float('inf') else 0.,
                f30=t30/teff*100, f24=t24/teff*100,
                f18=t18/teff*100, f0=t0/teff*100,
                flow_buf=tlow/teff*100, max_gap=max_gap)

def parse_iperf(path):
    if not path.exists(): return None
    c = path.read_text(errors='ignore')
    m = re.search(
        r'\[\s*\d+\]\s+0\.00-\d+\.\d+\s+sec\s+(\d+\.?\d*)\s+MBytes\s+'
        r'(\d+\.?\d*)\s+(Kbits|Mbits)/sec\s+(\d+\.?\d*)\s+ms\s+'
        r'(\d+)/(\d+)\s+\((\d+\.?\d*)%\)\s+receiver', c)
    if not m: return None
    rate = float(m.group(2)) * (1000 if m.group(3)=="Mbits" else 1)
    return dict(rate_kbps=rate, jitter_ms=float(m.group(4)),
                loss_pct=float(m.group(7)),
                lost=int(m.group(5)), total=int(m.group(6)))

def parse_int(path):
    if not path.exists(): return None
    q1e,q2e,q3e,d1,d2,d3=[],[],[],[],[],[]
    cnt=0
    for line in path.read_text(errors='ignore').splitlines():
        p = line.strip().split(",")
        if len(p) >= 31:
            try:
                q3e.append(int(p[7])); d3.append(int(p[8]))
                q2e.append(int(p[17])); d2.append(int(p[18]))
                q1e.append(int(p[27])); d1.append(int(p[28]))
                cnt+=1
            except (ValueError,IndexError): pass
    if cnt==0: return None
    return dict(n=cnt,
        q1_med=pct(q1e,0.5), q1_p95=pct(q1e,0.95),
        q2_med=pct(q2e,0.5), q2_p95=pct(q2e,0.95),
        q3_med=pct(q3e,0.5), q3_p95=pct(q3e,0.95),
        d1_mean=np.mean(d1) if d1 else 0.,
        d2_mean=np.mean(d2) if d2 else 0.,
        d3_mean=np.mean(d3) if d3 else 0.,
        e2e_delay_us=np.mean(d1)+np.mean(d2)+np.mean(d3) if d1 else 0.)

def parse_ctrl(run_tag):
    ap = AGENT_V2 / f"action_history_{run_tag}.csv"
    dp = AGENT_V2 / f"sw1_target_delay_history_{run_tag}.csv"
    res = dict(n_act=0,a0=0,a1=0,a2=0,
               d_init=50000,d_final=50000,d_mean=50000.,delays=[])
    if ap.exists():
        acts = []
        for l in ap.read_text(errors='ignore').splitlines():
            try: acts.append(int(l.strip()))
            except ValueError: pass
        res.update(n_act=len(acts),a0=acts.count(0),a1=acts.count(1),a2=acts.count(2))
    if dp.exists():
        ds = []
        for l in dp.read_text(errors='ignore').splitlines():
            try: ds.append(int(l.strip()))
            except ValueError: pass
        if ds:
            res.update(d_init=ds[0],d_final=ds[-1],
                       d_mean=float(np.mean(ds)),delays=ds)
    return res

# ── Discover all eval runs in campaign_v2 ────────────────────────────────────
def discover_runs():
    runs = []
    for pol_key, pol_name in POL_PREFIX.items():
        dash_files = sorted(V2_LOGS.glob(f"dash_v2_{pol_key}_eval_*.txt"))
        for df in dash_files:
            tag = df.stem.replace("dash_v2_","")  # e.g. fixed20k_eval_1
            run_tag = f"v2_{tag}"
            runs.append(dict(run_tag=run_tag, pol_key=pol_key,
                             policy=pol_name, tag=tag))
    return runs

# ── Main analysis ─────────────────────────────────────────────────────────────
def main():
    RESULTS.mkdir(parents=True, exist_ok=True)
    FIGS.mkdir(parents=True, exist_ok=True)

    runs = discover_runs()
    print(f"[*] Found {len(runs)} eval runs in campaign_v2")

    rows = []
    for r in runs:
        tag = r['tag']; run_tag = r['run_tag']; pol = r['policy']
        dash = parse_dash(V2_LOGS / f"dash_v2_{tag}.txt")
        iperf = parse_iperf(V2_LOGS / f"iperf_client_v2_{tag}.log")
        int_ = parse_int(V2_LOGS / f"log_INT_v2_{tag}.txt")
        ctrl = parse_ctrl(run_tag)

        if not dash:
            print(f"  [skip] {run_tag}: no dash"); continue

        entry = dict(run_id=run_tag, policy=pol,
            dur_s=dash['dur'], dash_n=dash['n'],
            mean_fps=dash['mean_fps'], med_fps=dash['med_fps'],
            mean_br=dash['mean_br'],
            mean_buf=dash['mean_buf'], min_buf=dash['min_buf'],
            f30=dash['f30'], f24=dash['f24'], f18=dash['f18'], f0=dash['f0'],
            flow_buf=dash['flow_buf'],
            rate_kbps=iperf['rate_kbps'] if iperf else 0,
            loss_pct=iperf['loss_pct'] if iperf else 0,
            jitter_ms=iperf['jitter_ms'] if iperf else 0,
            int_n=int_['n'] if int_ else 0,
            q3_p95=int_['q3_p95'] if int_ else 0,
            e2e_us=int_['e2e_delay_us'] if int_ else 0,
            n_act=ctrl['n_act'], a0=ctrl['a0'], a1=ctrl['a1'], a2=ctrl['a2'],
            d_init=ctrl['d_init'], d_final=ctrl['d_final'], d_mean=ctrl['d_mean'],
        )
        rows.append(entry)
        print(f"  [ok] {run_tag:35s} | {pol:12s} | FPS={entry['mean_fps']:.1f} | "
              f"30fps={entry['f30']:.0f}% | stall={entry['f0']:.1f}% | "
              f"buf={entry['mean_buf']:.1f}s | loss={entry['loss_pct']:.2f}%")

    if not rows:
        print("[!] No data found."); return

    df = pd.DataFrame(rows)
    df.to_csv(RESULTS/"run_summary_v2.csv", index=False)
    print(f"\n[+] Saved run_summary_v2.csv ({len(df)} runs)")

    # ── Aggregate per policy ───────────────────────────────────────────────────
    METRICS = ["mean_fps","f30","f0","mean_buf","min_buf","flow_buf",
               "mean_br","rate_kbps","loss_pct","jitter_ms","e2e_us","q3_p95"]

    agg = []
    for pol in POLICY_ORDER:
        sub = df[df['policy']==pol]
        if sub.empty: continue
        n = len(sub)
        row = {"policy":pol,"n":n}
        for m in METRICS:
            if m not in sub.columns: continue
            vals = sub[m].values
            mn = float(np.mean(vals))
            sd = float(np.std(vals,ddof=1)) if n>1 else 0.
            ci = ci95(list(vals)) if n>1 else 0.
            row[f"{m}_mean"]=mn; row[f"{m}_sd"]=sd; row[f"{m}_ci"]=ci
            row[f"{m}_fmt"]=(f"{mn:.2f} ± {sd:.2f} [CI±{ci:.2f}]"
                             if n>1 else f"{mn:.2f}")
        agg.append(row)

    df_agg = pd.DataFrame(agg)
    df_agg.to_csv(RESULTS/"policy_comparison_v2.csv", index=False)
    print(f"[+] Saved policy_comparison_v2.csv")

    # ── Figures ────────────────────────────────────────────────────────────────
    present_pols = [p for p in POLICY_ORDER if p in df_agg['policy'].values]
    colors = [COLORS[p] for p in present_pols]
    hatches = [HATCHES[p] for p in present_pols]
    x = np.arange(len(present_pols))

    def bar_ax(ax, means, errs, ylabel, title, fmt="{:.1f}", ylim=None, baseline=None):
        bars = ax.bar(x, means, yerr=errs, capsize=5,
                      color=colors, alpha=0.85, edgecolor='#111', linewidth=0.7)
        for bar, h in zip(bars, hatches):
            bar.set_hatch(h)
        ax.set_xticks(x)
        ax.set_xticklabels(present_pols, rotation=28, ha='right', fontsize=9)
        ax.set_ylabel(ylabel, fontsize=10)
        ax.set_title(title, fontsize=11, fontweight='bold', pad=6)
        if ylim: ax.set_ylim(*ylim)
        if baseline is not None:
            ax.axhline(baseline, ls='--', lw=1, color='#555')
        for i,(v,e) in enumerate(zip(means,errs)):
            pad = max(e, abs(v)*0.03) + (ylim[1]-ylim[0])*0.02 if ylim else e+1
            ax.text(i, v+pad, fmt.format(v), ha='center', fontsize=8, fontweight='bold')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

    def get(metric):
        return ([float(df_agg.loc[df_agg['policy']==p, f'{metric}_mean'].values[0])
                 if p in df_agg['policy'].values else 0 for p in present_pols],
                [float(df_agg.loc[df_agg['policy']==p, f'{metric}_ci'].values[0])
                 if p in df_agg['policy'].values else 0 for p in present_pols])

    # Figure 1: QoE – FPS + 30-FPS availability
    fig, (ax1,ax2) = plt.subplots(1,2,figsize=(13,5.5))
    fig.suptitle("DESiRED: Video QoE Across AQM Control Policies",
                 fontsize=13, fontweight='bold')
    m,e = get('mean_fps')
    bar_ax(ax1, m, e, "Duration-Weighted Mean FPS",
           "(a) Mean Video Playback Frame Rate", "{:.1f}", (0,34))
    m,e = get('f30')
    bar_ax(ax2, m, e, "Session Time at 30 FPS (%)",
           "(b) High-Quality (30 FPS) Availability", "{:.1f}%", (0,110))
    plt.tight_layout()
    plt.savefig(FIGS/"v2_qoe_fps.png", dpi=300, bbox_inches='tight')
    plt.close(); print("[+] Saved figs/v2_qoe_fps.png")

    # Figure 2: Buffer & Stalls
    fig, (ax1,ax2) = plt.subplots(1,2,figsize=(13,5.5))
    fig.suptitle("DESiRED: Video Buffer Level and Rebuffer Rate",
                 fontsize=13, fontweight='bold')
    m,e = get('mean_buf')
    bar_ax(ax1, m, e, "Mean Buffer Level (seconds)",
           "(a) Mean Video Playback Buffer", "{:.1f}s")
    m,e = get('f0')
    bar_ax(ax2, m, e, "Rebuffer / Stall Time (%)",
           "(b) Stall Ratio (FPS = 0)", "{:.1f}%")
    plt.tight_layout()
    plt.savefig(FIGS/"v2_buffer_stall.png", dpi=300, bbox_inches='tight')
    plt.close(); print("[+] Saved figs/v2_buffer_stall.png")

    # Figure 3: Network – loss & jitter
    fig, (ax1,ax2) = plt.subplots(1,2,figsize=(13,5.5))
    fig.suptitle("DESiRED: Network QoS Under 500 kbps Competing UDP Load",
                 fontsize=13, fontweight='bold')
    m,e = get('loss_pct')
    bar_ax(ax1, m, e, "UDP Datagram Loss (%)",
           "(a) Packet Loss Rate", "{:.2f}%")
    m,e = get('jitter_ms')
    bar_ax(ax2, m, e, "Receiver Jitter (ms)",
           "(b) UDP Delay Jitter", "{:.1f} ms")
    plt.tight_layout()
    plt.savefig(FIGS/"v2_network.png", dpi=300, bbox_inches='tight')
    plt.close(); print("[+] Saved figs/v2_network.png")

    # Figure 4: Target delay trajectory (RL & Rule runs)
    ctrl_df = df[df['policy'].isin(["RL-DDQN","Rule-Based"])]
    fig, ax = plt.subplots(figsize=(12,4.5))
    plotted = set()
    for _, row in ctrl_df.iterrows():
        pol = row['policy']
        dp = AGENT_V2 / f"sw1_target_delay_history_{row['run_id']}.csv"
        if not dp.exists(): continue
        ds = []
        for l in dp.read_text(errors='ignore').splitlines():
            try: ds.append(int(l.strip()))
            except ValueError: pass
        if not ds: continue
        t = [i*10 for i in range(len(ds))]
        lbl = pol if pol not in plotted else "_nolegend_"
        ax.plot(t, np.array(ds)/1000., color=COLORS[pol],
                alpha=0.65, linewidth=1.5, label=lbl)
        plotted.add(pol)
    ax.axhline(20, ls='--', lw=1, color='#999', label='Min (20ms)')
    ax.axhline(70, ls=':', lw=1, color='#999', label='Max (70ms)')
    ax.set_xlabel("Elapsed Time (s)", fontsize=11)
    ax.set_ylabel("Target Delay (ms)", fontsize=11)
    ax.set_title("DESiRED: Controller Target Delay Trajectory",
                 fontsize=12, fontweight='bold')
    ax.set_ylim(15,75); ax.set_xlim(0)
    ax.legend(fontsize=9, loc='upper right')
    ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
    plt.tight_layout()
    plt.savefig(FIGS/"v2_delay_trajectory.png", dpi=300, bbox_inches='tight')
    plt.close(); print("[+] Saved figs/v2_delay_trajectory.png")

    # Figure 5: INT queue depth (p95) across hops and policies
    fig, axes = plt.subplots(1,3,figsize=(14,5))
    fig.suptitle("DESiRED: INT-Measured Queue Occupancy (95th Percentile)",
                 fontsize=12, fontweight='bold')
    for hi, (ax, hop_key, hlabel) in enumerate(zip(
            axes,
            ['q1_p95','q2_p95','q3_p95'],
            ['Switch s1 (Hop 1)','Switch s2 (Hop 2)','Switch s3 (Hop 3)'])):
        means = []
        for pol in present_pols:
            sub = df[df['policy']==pol]
            if hop_key in sub.columns:
                means.append(float(sub[hop_key].mean()))
            else:
                means.append(0.)
        bars = ax.bar(x, means, color=colors, alpha=0.85, edgecolor='#111', linewidth=0.7)
        for bar, h in zip(bars, hatches): bar.set_hatch(h)
        ax.set_xticks(x)
        ax.set_xticklabels(present_pols, rotation=28, ha='right', fontsize=8)
        ax.set_ylabel("Queue Depth (packets)" if hi==0 else "", fontsize=9)
        ax.set_title(hlabel, fontsize=10, fontweight='bold')
        ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
        for i,v in enumerate(means):
            ax.text(i, v+0.5, f"{v:.0f}", ha='center', fontsize=8, fontweight='bold')
    plt.tight_layout()
    plt.savefig(FIGS/"v2_int_queue.png", dpi=300, bbox_inches='tight')
    plt.close(); print("[+] Saved figs/v2_int_queue.png")

    # ── Paper results report ───────────────────────────────────────────────────
    write_report(df, df_agg, agg, present_pols)

def write_report(df, df_agg, agg, present_pols):
    lines = []
    lines.append("# DESiRED — Final Evaluation Results (Campaign v2)\n")
    lines.append(f"*{len(df)} runs across {len(present_pols)} policies. "
                 "All metrics duration-weighted. 95% CI using Student's t.*\n")

    lines.append("\n## 1. Per-Run Metrics\n")
    lines.append("| Run ID | Policy | FPS | 30fps% | Stall% | Buf(s) | Loss% | Jitter(ms) | INT probes |")
    lines.append("|--------|--------|-----|--------|--------|--------|-------|-----------|------------|")
    for _,r in df.sort_values(['policy','run_id']).iterrows():
        lines.append(f"| `{r.run_id}` | {r.policy} | {r.mean_fps:.1f} | "
                     f"{r.f30:.1f} | {r.f0:.2f} | {r.mean_buf:.1f} | "
                     f"{r.loss_pct:.2f} | {r.jitter_ms:.1f} | {int(r.int_n)} |")

    lines.append("\n## 2. Policy Statistics (Mean ± SD, 95% CI)\n")
    lines.append("| Policy | N | Mean FPS | 30fps% | Stall% | Mean Buf (s) | Loss% | Jitter (ms) | E2E Delay (µs) |")
    lines.append("|--------|---|----------|--------|--------|-------------|-------|-------------|----------------|")
    for r in agg:
        def g(k): return r.get(f'{k}_fmt','—')
        lines.append(f"| **{r['policy']}** | {r['n']} | {g('mean_fps')} | "
                     f"{g('f30')} | {g('f0')} | {g('mean_buf')} | "
                     f"{g('loss_pct')} | {g('jitter_ms')} | {g('e2e_us')} |")

    lines.append("\n## 3. Key Findings\n")
    if agg:
        best_fps   = max(agg, key=lambda r: r.get('mean_fps_mean',0))
        best_30fps = max(agg, key=lambda r: r.get('f30_mean',0))
        best_buf   = max(agg, key=lambda r: r.get('mean_buf_mean',0))
        low_stall  = min(agg, key=lambda r: r.get('f0_mean',99))
        low_loss   = min(agg, key=lambda r: r.get('loss_pct_mean',99))
        lines.append(f"- **Highest mean FPS:** {best_fps['policy']} — {best_fps.get('mean_fps_fmt','?')}")
        lines.append(f"- **Best 30-FPS availability:** {best_30fps['policy']} — {best_30fps.get('f30_fmt','?')}")
        lines.append(f"- **Highest mean video buffer:** {best_buf['policy']} — {best_buf.get('mean_buf_fmt','?')} s")
        lines.append(f"- **Lowest stall ratio:** {low_stall['policy']} — {low_stall.get('f0_fmt','?')}")
        lines.append(f"- **Lowest UDP packet loss:** {low_loss['policy']} — {low_loss.get('loss_pct_fmt','?')}")

        # RL vs Fixed-50k (same initial delay)
        rl  = next((r for r in agg if r['policy']=='RL-DDQN'),None)
        f50 = next((r for r in agg if r['policy']=='Fixed-50k'),None)
        f20 = next((r for r in agg if r['policy']=='Fixed-20k'),None)
        rule= next((r for r in agg if r['policy']=='Rule-Based'),None)
        if rl and f50:
            d_fps = rl['mean_fps_mean']-f50['mean_fps_mean']
            d_30 = rl['f30_mean']-f50['f30_mean']
            d_stall = f50['f0_mean']-rl['f0_mean']
            lines.append(f"\n### RL-DDQN vs. Fixed-50k (same initial delay)")
            lines.append(f"- FPS improvement: **{d_fps:+.1f}** fps")
            lines.append(f"- 30-FPS availability gain: **{d_30:+.1f}%**")
            lines.append(f"- Stall ratio reduction: **{d_stall:+.1f}%**")
        if rl and f20:
            d_fps = rl['mean_fps_mean']-f20['mean_fps_mean']
            d_30  = rl['f30_mean']-f20['f30_mean']
            lines.append(f"\n### RL-DDQN vs. Fixed-20k (strictest static)")
            lines.append(f"- FPS difference: **{d_fps:+.1f}** fps")
            lines.append(f"- 30-FPS availability difference: **{d_30:+.1f}%**")
        if rule and f50:
            d_fps = rule['mean_fps_mean']-f50['mean_fps_mean']
            d_30 = rule['f30_mean']-f50['f30_mean']
            lines.append(f"\n### Rule-Based vs. Fixed-50k")
            lines.append(f"- FPS improvement: **{d_fps:+.1f}** fps")
            lines.append(f"- 30-FPS availability gain: **{d_30:+.1f}%**")

    lines.append("\n## 4. Controller Dynamics (RL & Rule Runs)\n")
    ctrl_df = df[df['policy'].isin(['RL-DDQN','Rule-Based'])].copy()
    if not ctrl_df.empty:
        lines.append("| Run ID | Policy | Actions | ↑Inc | ↓Dec | →Hold | "
                     "Initial Delay | Final Delay |")
        lines.append("|--------|--------|---------|------|------|-------|"
                     "-------------|-------------|")
        for _,r in ctrl_df.sort_values(['policy','run_id']).iterrows():
            lines.append(f"| `{r.run_id}` | {r.policy} | {int(r.n_act)} | "
                         f"{int(r.a0)} | {int(r.a1)} | {int(r.a2)} | "
                         f"{int(r.d_init)} µs | {int(r.d_final)} µs |")
    else:
        lines.append("*No controller runs found.*\n")

    lines.append("\n## 5. Generated Figures\n")
    figs = [
        ("v2_qoe_fps.png","Mean FPS & 30-FPS availability per policy"),
        ("v2_buffer_stall.png","Buffer level & stall rate per policy"),
        ("v2_network.png","UDP loss & jitter under competing load"),
        ("v2_delay_trajectory.png","Controller target-delay over time (RL & Rule)"),
        ("v2_int_queue.png","INT queue depth (p95) per switch hop"),
    ]
    lines.append("| Filename | Description |")
    lines.append("|----------|-------------|")
    for fn,desc in figs:
        lines.append(f"| `figs/{fn}` | {desc} |")

    report = "\n".join(lines)+"\n"
    p = RESULTS/"paper_results_v2.md"
    p.write_text(report)
    print(f"[+] Saved results/paper_results_v2.md")
    print("\n" + "="*60)
    print("  ANALYSIS COMPLETE — results ready for paper writing")
    print("="*60)

if __name__ == "__main__":
    main()
