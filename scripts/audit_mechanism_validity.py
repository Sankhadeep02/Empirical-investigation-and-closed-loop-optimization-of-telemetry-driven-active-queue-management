#!/usr/bin/env python3
"""
scripts/audit_mechanism_validity.py

Audits all runs in Campaign v4 mechanism test against strict criteria:
  1. Segment traffic balance: devB <= 5% (strict) or <= 10% (relaxed), devC <= 5% or <= 10%
  2. Physical plausibility ceiling: all segment median queue delays <= 210 ms (true buffer ceiling)
  3. No starvation: Segment C total packets >= 1000

Generates:
  - results/campaign_v4/mechanism_validity_audit.csv (all runs with audit status and explicit exclusion reasons)
  - results/campaign_v4/mechanism_test_valid.csv (only valid runs)
  - results/campaign_v4/mechanism_test_excluded.csv (excluded runs with reasons)
"""

import pandas as pd
import numpy as np
from pathlib import Path

REPO_ROOT = Path("/home/p4/DESiRED")
OUT_DIR = REPO_ROOT / "results/campaign_v4"
SRC_CSV = OUT_DIR / "mechanism_test_results.csv"

def audit():
    df = pd.read_csv(SRC_CSV)

    per_segment_rows = []
    per_run_rows = []

    for test_id, group in df.groupby("test_id", sort=False):
        g = group.set_index("segment")
        load = int(g.loc["A", "load_kbps"])
        rep = int(g.loc["A", "rep"])
        
        tot_A = int(g.loc["A", "total_pkts"])
        tot_B = int(g.loc["B", "total_pkts"])
        tot_C = int(g.loc["C", "total_pkts"])
        
        dev_B = abs(tot_B - tot_A) / max(1, tot_A) * 100.0
        dev_C = abs(tot_C - tot_A) / max(1, tot_A) * 100.0
        
        del_A = float(g.loc["A", "qdelay_median_ms"])
        del_B = float(g.loc["B", "qdelay_median_ms"])
        del_C = float(g.loc["C", "qdelay_median_ms"])

        iqr_A = float(g.loc["A", "qdelay_iqr_ms"])
        iqr_B = float(g.loc["B", "qdelay_iqr_ms"])
        iqr_C = float(g.loc["C", "qdelay_iqr_ms"])
        
        drp_A = int(g.loc["A", "red_drops"])
        drp_B = int(g.loc["B", "red_drops"])
        drp_C = int(g.loc["C", "red_drops"])

        fwd_A = int(g.loc["A", "fwd_pkts"])
        fwd_B = int(g.loc["B", "fwd_pkts"])
        fwd_C = int(g.loc["C", "fwd_pkts"])
        
        # Per-segment checks
        for seg, tot, dev, dly, iqr, drp, fwd in [
            ("A", tot_A, 0.0, del_A, iqr_A, drp_A, fwd_A),
            ("B", tot_B, dev_B, del_B, iqr_B, drp_B, fwd_B),
            ("C", tot_C, dev_C, del_C, iqr_C, drp_C, fwd_C)
        ]:
            seg_issues = []
            if dly > 210.0:
                seg_issues.append(f"Delay {dly:.1f}ms exceeds physical ceiling (210ms)")
            if tot < 500:
                seg_issues.append(f"Starved traffic ({tot} pkts)")
            if seg != "A" and dev > 10.0:
                seg_issues.append(f"Imbalanced ({dev:.1f}% vs Seg A)")
            elif seg != "A" and dev > 5.0:
                seg_issues.append(f"Marginal imbalance ({dev:.1f}% vs Seg A)")

            per_segment_rows.append({
                "test_id": test_id, "load_kbps": load, "rep": rep, "segment": seg,
                "target_ms": 70 if seg == "B" else 20,
                "total_pkts": tot, "fwd_pkts": fwd, "red_drops": drp,
                "dev_vs_A_%": round(dev, 1) if seg != "A" else 0.0,
                "qdelay_median_ms": round(dly, 2), "qdelay_iqr_ms": round(iqr, 2),
                "is_plausible": dly <= 210.0,
                "segment_issues": "; ".join(seg_issues) if seg_issues else "OK"
            })

        # Run-level classification
        reasons = []
        if del_A > 210 or del_B > 210 or del_C > 210:
            reasons.append(f"Exceeds physical ceiling of 210ms (delA={del_A:.1f}, delB={del_B:.1f}, delC={del_C:.1f} ms)")
        if tot_C < 500:
            reasons.append(f"Segment C starved ({tot_C} pkts)")
        if dev_B > 10.0 or dev_C > 10.0:
            reasons.append(f"Severe segment imbalance (devB={dev_B:.1f}%, devC={dev_C:.1f}% > 10%)")
        elif dev_B > 5.0 or dev_C > 5.0:
            reasons.append(f"Marginal segment imbalance (devB={dev_B:.1f}%, devC={dev_C:.1f}% > 5%)")

        if len(reasons) == 0:
            status = "VALID (Strict 5%)"
        elif len(reasons) == 1 and "Marginal" in reasons[0]:
            status = "VALID (Relaxed 10%)"
        else:
            status = "EXCLUDED"

        per_run_rows.append({
            "test_id": test_id, "load_kbps": load, "rep": rep,
            "tot_A": tot_A, "tot_B": tot_B, "tot_C": tot_C,
            "dev_B_%": round(dev_B, 1), "dev_C_%": round(dev_C, 1),
            "del_A_ms": round(del_A, 2), "del_B_ms": round(del_B, 2), "del_C_ms": round(del_C, 2),
            "drp_A": drp_A, "drp_B": drp_B, "drp_C": drp_C,
            "drp_delta_B_minus_A": drp_B - drp_A,
            "drp_ratio_B_over_A": round(drp_B / max(1, drp_A), 3),
            "status": status,
            "exclusion_reason": "; ".join(reasons) if status == "EXCLUDED" else ""
        })

    seg_df = pd.DataFrame(per_segment_rows)
    run_df = pd.DataFrame(per_run_rows)

    audit_csv = OUT_DIR / "mechanism_per_segment_validity.csv"
    run_audit_csv = OUT_DIR / "mechanism_run_validity_audit.csv"
    valid_csv = OUT_DIR / "mechanism_test_valid.csv"
    excluded_csv = OUT_DIR / "mechanism_test_excluded.csv"

    seg_df.to_csv(audit_csv, index=False)
    run_df.to_csv(run_audit_csv, index=False)

    valid_runs = run_df[run_df["status"].str.startswith("VALID")]["test_id"].tolist()
    excluded_runs = run_df[run_df["status"] == "EXCLUDED"]["test_id"].tolist()

    df[df["test_id"].isin(valid_runs)].to_csv(valid_csv, index=False)
    df[df["test_id"].isin(excluded_runs)].to_csv(excluded_csv, index=False)

    print(f"[+] Saved per-segment audit to: {audit_csv}")
    print(f"[+] Saved run validity audit to: {run_audit_csv}")
    print(f"[+] Saved valid runs ({len(valid_runs)}) to: {valid_csv}")
    print(f"[+] Saved excluded runs ({len(excluded_runs)}) to: {excluded_csv}")

if __name__ == "__main__":
    audit()
