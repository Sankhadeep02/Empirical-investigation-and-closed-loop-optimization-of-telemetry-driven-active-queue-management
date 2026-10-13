#!/usr/bin/env python3
from pathlib import Path
import bisect
import csv
import statistics as stats

INT_FILE = Path("/home/p4/DESiRED/src/logs/log_INT_iRED-RL_9.txt")
DASH_FILE = Path("/home/p4/DESiRED/src/logs/dash_iRED-RL_9.txt")
OUT_FILE = Path("/home/p4/DESiRED/src/logs/run9_joined_telemetry.csv")

HOP_FIELDS = [
    "swid",
    "ingress_port",
    "egress_port",
    "egress_spec",
    "ingress_global_timestamp",
    "egress_global_timestamp",
    "enq_timestamp",
    "enq_qdepth",
    "deq_timedelta",
    "deq_qdepth",
]

def percentile(values, p):
    ordered = sorted(values)
    if not ordered:
        return None
    index = round((len(ordered) - 1) * p)
    return ordered[index]

def summary(values):
    return {
        "count": len(values),
        "min": min(values),
        "mean": stats.mean(values),
        "median": stats.median(values),
        "p95": percentile(values, 0.95),
        "max": max(values),
    }

def print_summary(label, values, decimals=2):
    s = summary(values)
    print(
        f"{label}: count={s['count']}, min={s['min']}, "
        f"mean={s['mean']:.{decimals}f}, median={s['median']:.{decimals}f}, "
        f"p95={s['p95']}, max={s['max']}"
    )

def parse_dash():
    rows = []
    with DASH_FILE.open() as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            fields = line.split(";")
            if len(fields) != 4:
                raise ValueError(f"DASH line {line_number}: expected 4 fields, got {len(fields)}")
            rows.append(
                {
                    "timestamp_ms": int(fields[0]),
                    "buffer_seconds": float(fields[1]),
                    "fps": int(fields[2]),
                    "bitrate_kbps": int(fields[3]),
                }
            )
    return rows

def nearest_dash(int_timestamp, dash_rows, dash_timestamps):
    index = bisect.bisect_left(dash_timestamps, int_timestamp)

    candidates = []
    if index < len(dash_rows):
        candidates.append(dash_rows[index])
    if index > 0:
        candidates.append(dash_rows[index - 1])

    return min(candidates, key=lambda row: abs(row["timestamp_ms"] - int_timestamp))

dash_rows = parse_dash()
dash_timestamps = [row["timestamp_ms"] for row in dash_rows]

joined_rows = []
with INT_FILE.open(newline="") as f:
    reader = csv.reader(f)
    for line_number, row in enumerate(reader, start=1):
        if not row:
            continue
        if len(row) != 31:
            raise ValueError(f"INT line {line_number}: expected 31 fields, got {len(row)}")

        receiver_timestamp_ms = int(row[0])
        output = {
            "receiver_timestamp_ms": receiver_timestamp_ms,
        }

        total_ingress_egress_delta = 0
        total_deq_timedelta = 0

        for hop_number in range(1, 4):
            start = 1 + (hop_number - 1) * 10
            values = [int(value) for value in row[start:start + 10]]
            hop = dict(zip(HOP_FIELDS, values))

            ingress_egress_delta = (
                hop["egress_global_timestamp"] - hop["ingress_global_timestamp"]
            )

            prefix = f"hop{hop_number}_"
            for field_name, value in hop.items():
                output[prefix + field_name] = value

            output[prefix + "ingress_egress_delta"] = ingress_egress_delta
            total_ingress_egress_delta += ingress_egress_delta
            total_deq_timedelta += hop["deq_timedelta"]

        matched_dash = nearest_dash(
            receiver_timestamp_ms, dash_rows, dash_timestamps
        )

        output["total_ingress_egress_delta"] = total_ingress_egress_delta
        output["total_deq_timedelta"] = total_deq_timedelta
        output["dash_timestamp_ms"] = matched_dash["timestamp_ms"]
        output["dash_match_offset_ms"] = (
            receiver_timestamp_ms - matched_dash["timestamp_ms"]
        )
        output["buffer_seconds"] = matched_dash["buffer_seconds"]
        output["fps"] = matched_dash["fps"]
        output["bitrate_kbps"] = matched_dash["bitrate_kbps"]

        joined_rows.append(output)

fieldnames = list(joined_rows[0].keys())
with OUT_FILE.open("w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(joined_rows)

print("=== PARSE COMPLETE ===")
print(f"INT rows parsed: {len(joined_rows)}")
print(f"DASH rows parsed: {len(dash_rows)}")
print(f"Joined CSV written: {OUT_FILE}")
print()

for hop_number in range(1, 4):
    print_summary(
        f"Hop {hop_number} enqueue queue depth",
        [row[f"hop{hop_number}_enq_qdepth"] for row in joined_rows],
        decimals=2,
    )
    print_summary(
        f"Hop {hop_number} dequeue queue depth",
        [row[f"hop{hop_number}_deq_qdepth"] for row in joined_rows],
        decimals=2,
    )
    print_summary(
        f"Hop {hop_number} dequeue timedelta",
        [row[f"hop{hop_number}_deq_timedelta"] for row in joined_rows],
        decimals=2,
    )
    print_summary(
        f"Hop {hop_number} ingress-to-egress delta",
        [row[f"hop{hop_number}_ingress_egress_delta"] for row in joined_rows],
        decimals=2,
    )
    print()

print_summary(
    "Total three-hop dequeue timedelta",
    [row["total_deq_timedelta"] for row in joined_rows],
    decimals=2,
)
print_summary(
    "DASH buffer (seconds)",
    [row["buffer_seconds"] for row in joined_rows],
    decimals=2,
)
print_summary(
    "DASH FPS",
    [row["fps"] for row in joined_rows],
    decimals=2,
)
print_summary(
    "DASH bitrate (kbps)",
    [row["bitrate_kbps"] for row in joined_rows],
    decimals=2,
)
print_summary(
    "INT-to-DASH timestamp offset (ms)",
    [row["dash_match_offset_ms"] for row in joined_rows],
    decimals=2,
)
