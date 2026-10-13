#!/usr/bin/env python3
"""
scripts/measure_bottleneck_capacity.py

Measures the empirical bottleneck capacity through Switch 2 (s1 -> s2 -> s3 -> h4)
under Campaign v4 settings (no switch console logging).
Target delay is set high (500,000 us = 500 ms) so AQM stays out of the way.
Offers UDP loads from 500 kbps up to 3000 kbps to map the true throughput curve.
"""

import sys
import time
import re
import subprocess
from pathlib import Path
import pandas as pd

REPO_ROOT = Path("/home/p4/DESiRED")
OUT_DIR = REPO_ROOT / "results/campaign_v4"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_CSV = OUT_DIR / "bottleneck_capacity_curve.csv"

# Test loads in kbps
OFFERED_LOADS_KBPS = [500, 1000, 1500, 1800, 2000, 2200, 2400, 2600, 2800, 3000]
STEP_DURATION_S = 15

def main():
    print("=================================================================")
    print("CAMPAIGN v4: BOTTLENECK CAPACITY CURVE MEASUREMENT")
    print(f"Setting AQM target delay to 500,000 us (inactive)")
    print(f"Testing offered loads: {OFFERED_LOADS_KBPS} kbps")
    print("=================================================================")

    # Set target delay high on all switches
    for port in [9090, 9091, 9092]:
        subprocess.run(
            f"echo 'register_write MyEgress.targetDelay_reg 0 500000' | simple_switch_CLI --thrift-port {port}",
            shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

    # Ensure bottleneck shaping on s2 port 2
    subprocess.run(
        "echo -e 'set_queue_rate 200 2\nset_queue_depth 32 2' | simple_switch_CLI --thrift-port 9091",
        shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    results = []

    for load_kbps in OFFERED_LOADS_KBPS:
        print(f"\n[*] Testing offered load: {load_kbps} kbps for {STEP_DURATION_S}s...")
        cmd = f"mx h3 iperf3 -c 10.0.0.4 -u -b {load_kbps}k -t {STEP_DURATION_S} -l 1470 -i 1"
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        out = res.stdout

        # Parse receiver throughput, loss, jitter
        # Sample line: [  8]   0.00-15.01  sec  3.90 MBytes  2.18 Mbits/sec  2.345 ms  120/2800 (4.2%)  receiver
        m_rec = re.findall(r"(\d+\.?\d*)\s+Mbits/sec\s+(\d+\.?\d*)\s+ms\s+\d+/\d+\s+\((\d+\.?\d*)%\)\s+receiver", out)
        if not m_rec:
            # Try Kbits/sec or generic
            m_rec = re.findall(r"(\d+\.?\d*)\s+([MK]bits/sec).+?\((\d+\.?\d*)%\)\s+receiver", out)
            if m_rec:
                val = float(m_rec[-1][0])
                unit = m_rec[-1][1]
                rec_mbps = val if "M" in unit else val / 1000.0
                loss_pct = float(m_rec[-1][2])
                jitter_ms = 0.0
            else:
                print(f"[!] Warning: Could not parse receiver line. Raw output:\n{out[-300:]}")
                rec_mbps, loss_pct, jitter_ms = 0.0, 100.0, 0.0
        else:
            rec_mbps = float(m_rec[-1][0])
            jitter_ms = float(m_rec[-1][1])
            loss_pct = float(m_rec[-1][2])

        goodput_kbps = rec_mbps * 1000.0
        print(f"    --> Goodput: {goodput_kbps:.1f} kbps | Loss: {loss_pct:.1f}% | Jitter: {jitter_ms:.2f} ms")

        results.append({
            "offered_kbps": load_kbps,
            "goodput_kbps": goodput_kbps,
            "loss_pct": loss_pct,
            "jitter_ms": jitter_ms
        })

        time.sleep(1.0)

    df = pd.DataFrame(results)
    df.to_csv(OUT_CSV, index=False)
    print(f"\n[+] Capacity curve saved to {OUT_CSV}")
    print("\nSummary Table:")
    print(df.to_string(index=False))

if __name__ == "__main__":
    main()
