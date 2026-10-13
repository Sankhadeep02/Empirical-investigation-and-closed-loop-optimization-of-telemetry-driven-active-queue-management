#!/usr/bin/env python3
from pathlib import Path
import csv
import statistics as stats

LOG_DIR = Path("/home/p4/DESiRED/src/logs")

RUNS = {
    "9": {
        "target_delay_us": 80000,
        "load": "none",
        "description": "Baseline; register remained zero, so P4 used 80 ms fallback",
    },
    "10": {
        "target_delay_us": 20000,
        "load": "10 Mbps UDP h1-to-h2",
        "description": "Congested; strict 20 ms AQM target",
    },
    "11": {
        "target_delay_us": 50000,
        "load": "none",
        "description": "No-load reference; explicit 50 ms AQM target",
    },
    "12": {
        "target_delay_us": 50000,
        "load": "10 Mbps UDP h1-to-h2",
        "description": "Congested; moderate 50 ms AQM target",
    },
}

SUMMARY_COLUMNS = [
    "run_id",
    "observations",
    "target_delay_us",
    "load",
    "description",
    "hop1_qdepth_median",
    "hop2_qdepth_median",
    "hop3_qdepth_median",
    "hop3_qdepth_p95",
    "total_deq_median",
    "total_deq_p95",
    "buffer_median_s",
    "buffer_mean_s",
    "fps_median",
    "fps_mean",
    "bitrate_median_kbps",
    "bitrate_mean_kbps",
    "top_tier_percent",
    "stalled_percent",
]

def percentile(values, fraction):
    values = sorted(values)
    return values[round((len(values) - 1) * fraction)]

def as_ints(rows, field):
    return [int(row[field]) for row in rows]

def as_floats(rows, field):
    return [float(row[field]) for row in rows]

summary_rows = []

for run_id, metadata in RUNS.items():
    csv_path = LOG_DIR / f"run{run_id}_joined_telemetry.csv"

    if not csv_path.exists():
        print(f"Skipping run {run_id}: missing {csv_path}")
        continue

    with csv_path.open(newline="") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print(f"Skipping run {run_id}: empty CSV")
        continue

    hop1 = as_ints(rows, "hop1_enq_qdepth")
    hop2 = as_ints(rows, "hop2_enq_qdepth")
    hop3 = as_ints(rows, "hop3_enq_qdepth")
    total_deq = as_ints(rows, "total_deq_timedelta")
    buffers = as_floats(rows, "buffer_seconds")
    fps = as_ints(rows, "fps")
    bitrates = as_ints(rows, "bitrate_kbps")

    top_tier = sum(
        int(row["fps"]) == 30 and int(row["bitrate_kbps"]) == 1040
        for row in rows
    )
    stalled = sum(int(row["fps"]) == 0 for row in rows)

    summary_rows.append({
        "run_id": run_id,
        "observations": len(rows),
        "target_delay_us": metadata["target_delay_us"],
        "load": metadata["load"],
        "description": metadata["description"],
        "hop1_qdepth_median": stats.median(hop1),
        "hop2_qdepth_median": stats.median(hop2),
        "hop3_qdepth_median": stats.median(hop3),
        "hop3_qdepth_p95": percentile(hop3, 0.95),
        "total_deq_median": stats.median(total_deq),
        "total_deq_p95": percentile(total_deq, 0.95),
        "buffer_median_s": stats.median(buffers),
        "buffer_mean_s": round(stats.mean(buffers), 2),
        "fps_median": stats.median(fps),
        "fps_mean": round(stats.mean(fps), 2),
        "bitrate_median_kbps": stats.median(bitrates),
        "bitrate_mean_kbps": round(stats.mean(bitrates), 2),
        "top_tier_percent": round(100 * top_tier / len(rows), 2),
        "stalled_percent": round(100 * stalled / len(rows), 2),
    })

out_path = LOG_DIR / "runs_9_12_summary.csv"
with out_path.open("w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=SUMMARY_COLUMNS)
    writer.writeheader()
    writer.writerows(summary_rows)

print("=== DESiRED EXPERIMENT SUMMARY ===")
for row in summary_rows:
    print()
    print(
        f"Run {row['run_id']} | target={row['target_delay_us']} us | "
        f"load={row['load']} | observations={row['observations']}"
    )
    print(f"  {row['description']}")
    print(
        "  median qdepth (hop1/hop2/hop3): "
        f"{row['hop1_qdepth_median']} / "
        f"{row['hop2_qdepth_median']} / "
        f"{row['hop3_qdepth_median']}; "
        f"hop3 p95={row['hop3_qdepth_p95']}"
    )
    print(
        "  total dequeue timing median/p95: "
        f"{row['total_deq_median']} / {row['total_deq_p95']}"
    )
    print(
        "  DASH buffer median/mean: "
        f"{row['buffer_median_s']:.2f} / {row['buffer_mean_s']:.2f} s"
    )
    print(
        "  DASH FPS median/mean: "
        f"{row['fps_median']} / {row['fps_mean']}"
    )
    print(
        "  DASH bitrate median/mean: "
        f"{row['bitrate_median_kbps']} / {row['bitrate_mean_kbps']} kbps"
    )
    print(
        f"  top tier={row['top_tier_percent']}%; "
        f"stalled={row['stalled_percent']}%"
    )

print()
print(f"Wrote: {out_path}")
