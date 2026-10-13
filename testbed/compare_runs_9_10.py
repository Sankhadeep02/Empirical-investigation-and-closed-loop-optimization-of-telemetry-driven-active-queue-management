#!/usr/bin/env python3
from pathlib import Path
import csv
import statistics as stats

LOG_DIR = Path("/home/p4/DESiRED/src/logs")

RUNS = {
    "9": {
        "target_delay_us": 80000,
        "traffic_condition": "baseline: no iperf cross traffic",
    },
    "10": {
        "target_delay_us": 20000,
        "traffic_condition": "congested: h1-to-h2 UDP, 10 Mbps offered",
    },
}

COLUMNS = [
    "run_id",
    "observations",
    "target_delay_us",
    "traffic_condition",
    "hop1_enq_qdepth_median",
    "hop2_enq_qdepth_median",
    "hop3_enq_qdepth_median",
    "hop3_enq_qdepth_p95",
    "total_deq_timedelta_median",
    "total_deq_timedelta_p95",
    "buffer_seconds_median",
    "buffer_seconds_min",
    "fps_median",
    "bitrate_kbps_median",
    "top_tier_percent",
    "stalled_percent",
]

def percentile(values, fraction):
    values = sorted(values)
    return values[round((len(values) - 1) * fraction)]

def load_rows(run_id):
    path = LOG_DIR / f"run{run_id}_joined_telemetry.csv"
    with path.open(newline="") as f:
        return list(csv.DictReader(f))

def ints(rows, key):
    return [int(row[key]) for row in rows]

def floats(rows, key):
    return [float(row[key]) for row in rows]

summary = []

for run_id, metadata in RUNS.items():
    rows = load_rows(run_id)

    hop1_qdepth = ints(rows, "hop1_enq_qdepth")
    hop2_qdepth = ints(rows, "hop2_enq_qdepth")
    hop3_qdepth = ints(rows, "hop3_enq_qdepth")
    total_deq = ints(rows, "total_deq_timedelta")
    buffers = floats(rows, "buffer_seconds")
    fps = ints(rows, "fps")
    bitrates = ints(rows, "bitrate_kbps")

    observation_count = len(rows)
    top_tier_count = sum(
        row["fps"] == "30" and row["bitrate_kbps"] == "1040"
        for row in rows
    )
    stalled_count = sum(row["fps"] == "0" for row in rows)

    summary.append(
        {
            "run_id": run_id,
            "observations": observation_count,
            "target_delay_us": metadata["target_delay_us"],
            "traffic_condition": metadata["traffic_condition"],
            "hop1_enq_qdepth_median": stats.median(hop1_qdepth),
            "hop2_enq_qdepth_median": stats.median(hop2_qdepth),
            "hop3_enq_qdepth_median": stats.median(hop3_qdepth),
            "hop3_enq_qdepth_p95": percentile(hop3_qdepth, 0.95),
            "total_deq_timedelta_median": stats.median(total_deq),
            "total_deq_timedelta_p95": percentile(total_deq, 0.95),
            "buffer_seconds_median": stats.median(buffers),
            "buffer_seconds_min": min(buffers),
            "fps_median": stats.median(fps),
            "bitrate_kbps_median": stats.median(bitrates),
            "top_tier_percent": round(100 * top_tier_count / observation_count, 2),
            "stalled_percent": round(100 * stalled_count / observation_count, 2),
        }
    )

out_path = LOG_DIR / "runs_9_10_summary.csv"
with out_path.open("w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=COLUMNS)
    writer.writeheader()
    writer.writerows(summary)

print("=== RUN 9 VS RUN 10 SUMMARY ===")
for row in summary:
    print()
    print(f"Run {row['run_id']}: {row['traffic_condition']}")
    print(f"  observations: {row['observations']}")
    print(f"  target delay: {row['target_delay_us']} us")
    print(
        "  median enqueue qdepth (hop1/hop2/hop3): "
        f"{row['hop1_enq_qdepth_median']} / "
        f"{row['hop2_enq_qdepth_median']} / "
        f"{row['hop3_enq_qdepth_median']}"
    )
    print(f"  hop3 enqueue qdepth p95: {row['hop3_enq_qdepth_p95']}")
    print(
        "  total dequeue timing, median/p95: "
        f"{row['total_deq_timedelta_median']} / "
        f"{row['total_deq_timedelta_p95']}"
    )
    print(
        "  DASH buffer, median/min seconds: "
        f"{row['buffer_seconds_median']:.2f} / "
        f"{row['buffer_seconds_min']:.2f}"
    )
    print(f"  DASH FPS median: {row['fps_median']}")
    print(f"  DASH bitrate median: {row['bitrate_kbps_median']} kbps")
    print(f"  top-tier observations: {row['top_tier_percent']}%")
    print(f"  stalled observations (0 FPS): {row['stalled_percent']}%")

print()
print(f"Wrote CSV summary: {out_path}")
