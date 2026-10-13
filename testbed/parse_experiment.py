#!/usr/bin/env python3
from pathlib import Path
import argparse
import bisect
import csv
import statistics as stats

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

def percentile(values, fraction):
    values = sorted(values)
    return values[round((len(values) - 1) * fraction)]

def show_summary(name, values):
    print(
        f"{name}: count={len(values)}, min={min(values)}, "
        f"mean={stats.mean(values):.2f}, median={stats.median(values):.2f}, "
        f"p95={percentile(values, 0.95)}, max={max(values)}"
    )

def load_dash(path):
    rows = []
    with path.open() as f:
        for line_number, line in enumerate(f, start=1):
            fields = line.strip().split(";")
            if len(fields) != 4:
                if not line.strip():
                    continue
                raise ValueError(
                    f"{path}: line {line_number} has {len(fields)} fields; expected 4."
                )
            rows.append(
                {
                    "timestamp_ms": int(fields[0]),
                    "buffer_seconds": float(fields[1]),
                    "fps": int(fields[2]),
                    "bitrate_kbps": int(fields[3]),
                }
            )
    return rows

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id", help="Example: 10")
    args = parser.parse_args()

    run_id = args.run_id
    logs = Path("/home/p4/DESiRED/src/logs")
    int_path = logs / f"log_INT_iRED-RL_{run_id}.txt"
    dash_path = logs / f"dash_iRED-RL_{run_id}.txt"
    output_path = logs / f"run{run_id}_joined_telemetry.csv"

    if not int_path.exists():
        raise FileNotFoundError(f"Missing INT file: {int_path}")
    if not dash_path.exists():
        raise FileNotFoundError(f"Missing DASH file: {dash_path}")

    dash_rows = load_dash(dash_path)
    dash_timestamps = [row["timestamp_ms"] for row in dash_rows]

    joined_rows = []

    with int_path.open(newline="") as f:
        for line_number, row in enumerate(csv.reader(f), start=1):
            if not row:
                continue
            if len(row) != 31:
                raise ValueError(
                    f"{int_path}: line {line_number} has {len(row)} fields; expected 31."
                )

            receiver_timestamp_ms = int(row[0])
            result = {"receiver_timestamp_ms": receiver_timestamp_ms}
            total_ingress_egress_delta = 0
            total_deq_timedelta = 0

            for hop_number in range(1, 4):
                start = 1 + (hop_number - 1) * 10
                hop_values = [int(value) for value in row[start:start + 10]]
                hop = dict(zip(HOP_FIELDS, hop_values))
                prefix = f"hop{hop_number}_"

                for key, value in hop.items():
                    result[prefix + key] = value

                delta = (
                    hop["egress_global_timestamp"]
                    - hop["ingress_global_timestamp"]
                )
                result[prefix + "ingress_egress_delta"] = delta
                total_ingress_egress_delta += delta
                total_deq_timedelta += hop["deq_timedelta"]

            index = bisect.bisect_left(dash_timestamps, receiver_timestamp_ms)
            candidates = []
            if index > 0:
                candidates.append(dash_rows[index - 1])
            if index < len(dash_rows):
                candidates.append(dash_rows[index])

            dash = min(
                candidates,
                key=lambda candidate: abs(
                    candidate["timestamp_ms"] - receiver_timestamp_ms
                ),
            )

            result["total_ingress_egress_delta"] = total_ingress_egress_delta
            result["total_deq_timedelta"] = total_deq_timedelta
            result["dash_timestamp_ms"] = dash["timestamp_ms"]
            result["dash_match_offset_ms"] = (
                receiver_timestamp_ms - dash["timestamp_ms"]
            )
            result["buffer_seconds"] = dash["buffer_seconds"]
            result["fps"] = dash["fps"]
            result["bitrate_kbps"] = dash["bitrate_kbps"]
            joined_rows.append(result)

    with output_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=joined_rows[0].keys())
        writer.writeheader()
        writer.writerows(joined_rows)

    print(f"INT rows parsed: {len(joined_rows)}")
    print(f"DASH rows parsed: {len(dash_rows)}")
    print(f"Joined CSV: {output_path}")
    print()

    for hop in range(1, 4):
        show_summary(
            f"Hop {hop} enqueue queue depth",
            [row[f"hop{hop}_enq_qdepth"] for row in joined_rows],
        )
        show_summary(
            f"Hop {hop} dequeue queue depth",
            [row[f"hop{hop}_deq_qdepth"] for row in joined_rows],
        )
        show_summary(
            f"Hop {hop} dequeue timedelta",
            [row[f"hop{hop}_deq_timedelta"] for row in joined_rows],
        )
        print()

    show_summary(
        "Total dequeue timedelta",
        [row["total_deq_timedelta"] for row in joined_rows],
    )
    show_summary(
        "DASH buffer seconds",
        [row["buffer_seconds"] for row in joined_rows],
    )
    show_summary(
        "DASH FPS",
        [row["fps"] for row in joined_rows],
    )
    show_summary(
        "DASH bitrate kbps",
        [row["bitrate_kbps"] for row in joined_rows],
    )

if __name__ == "__main__":
    main()
