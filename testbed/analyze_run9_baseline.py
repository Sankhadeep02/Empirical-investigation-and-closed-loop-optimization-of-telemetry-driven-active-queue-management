#!/usr/bin/env python3
from pathlib import Path
import csv
import statistics as stats

FILE = Path("/home/p4/DESiRED/src/logs/run9_joined_telemetry.csv")

def percentile(values, p):
    values = sorted(values)
    return values[round((len(values) - 1) * p)]

def describe(values):
    return {
        "min": min(values),
        "mean": stats.mean(values),
        "median": stats.median(values),
        "p95": percentile(values, 0.95),
        "max": max(values),
    }

def show(name, values, digits=2):
    d = describe(values)
    print(
        f"{name}: min={d['min']}, mean={d['mean']:.{digits}f}, "
        f"median={d['median']:.{digits}f}, p95={d['p95']}, max={d['max']}"
    )

with FILE.open(newline="") as f:
    rows = list(csv.DictReader(f))

for row in rows:
    for key in row:
        if key in {"buffer_seconds"}:
            row[key] = float(row[key])
        elif key != "":
            try:
                row[key] = int(row[key])
            except ValueError:
                pass

buffers = [row["buffer_seconds"] for row in rows]
fps_values = [row["fps"] for row in rows]
bitrate_values = [row["bitrate_kbps"] for row in rows]
total_deq = [row["total_deq_timedelta"] for row in rows]
total_delta = [row["total_ingress_egress_delta"] for row in rows]
offsets = [row["dash_match_offset_ms"] for row in rows]

top_tier = sum(
    row["fps"] == 30 and row["bitrate_kbps"] == 1040
    for row in rows
)

middle_tier = sum(
    row["fps"] == 24 and row["bitrate_kbps"] == 490
    for row in rows
)

low_tier = sum(
    row["fps"] == 18 and row["bitrate_kbps"] == 140
    for row in rows
)

startup_cutoff_ms = rows[0]["receiver_timestamp_ms"] + 10_000
steady_rows = [
    row for row in rows
    if row["receiver_timestamp_ms"] >= startup_cutoff_ms
]
steady_offsets = [
    abs(row["dash_match_offset_ms"])
    for row in steady_rows
]

print("=== RUN 9 BASELINE REPORT ===")
print(f"Joined observations: {len(rows)}")
print()

print("=== DASH QoE ===")
show("Buffer level (seconds)", buffers)
print(f"Top tier (30 FPS, 1040 kbps): {top_tier}/{len(rows)} ({100 * top_tier / len(rows):.2f}%)")
print(f"Middle tier (24 FPS, 490 kbps): {middle_tier}/{len(rows)} ({100 * middle_tier / len(rows):.2f}%)")
print(f"Low tier (18 FPS, 140 kbps): {low_tier}/{len(rows)} ({100 * low_tier / len(rows):.2f}%)")
print()

print("=== INT DELAY ===")
show("Total dequeue timedelta", total_deq)
show("Total ingress-to-egress delta", total_delta)
for hop in range(1, 4):
    show(
        f"Hop {hop} dequeue timedelta",
        [row[f"hop{hop}_deq_timedelta"] for row in rows],
    )
print()

print("=== ALIGNMENT ===")
show("Absolute DASH match offset, all rows (ms)", [abs(x) for x in offsets])
show(
    "Absolute DASH match offset after first 10 seconds (ms)",
    steady_offsets,
)
print(f"Rows after startup exclusion: {len(steady_rows)}")
