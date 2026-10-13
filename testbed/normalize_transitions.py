#!/usr/bin/env python3
from pathlib import Path
import csv
import math

INPUT = Path("/home/p4/DESiRED/src/logs/dqn_transitions_runs_10_12_13.csv")
OUTPUT = Path("/home/p4/DESiRED/src/logs/dqn_transitions_normalized.csv")
STATS_OUTPUT = Path("/home/p4/DESiRED/src/logs/dqn_feature_scaling.csv")

FEATURES = [
    "hop2_enq_qdepth",
    "hop3_enq_qdepth",
    "total_deq_timedelta",
    "buffer_seconds",
    "fps",
    "bitrate_kbps",
]

def transform(feature, value):
    value = float(value)
    if feature == "total_deq_timedelta":
        return math.log1p(value)
    return value

with INPUT.open(newline="") as f:
    rows = list(csv.DictReader(f))

scaling = {}
for feature in FEATURES:
    values = [
        transform(feature, row[f"state_{feature}"])
        for row in rows
    ] + [
        transform(feature, row[f"next_state_{feature}"])
        for row in rows
    ]

    lower = min(values)
    upper = max(values)
    scaling[feature] = {"min": lower, "max": upper}

def normalize(feature, raw_value):
    value = transform(feature, raw_value)
    lower = scaling[feature]["min"]
    upper = scaling[feature]["max"]

    if upper == lower:
        return 0.0

    return (value - lower) / (upper - lower)

output_rows = []
for row in rows:
    result = {
        "run_id": row["run_id"],
        "target_delay_us": row["target_delay_us"],
        "action": row["action"],
        "timestamp_ms": row["timestamp_ms"],
        "reward": row["reward"],
        "done": row["done"],
    }

    for feature in FEATURES:
        result[f"state_{feature}"] = f"{normalize(feature, row[f'state_{feature}']):.8f}"
        result[f"next_state_{feature}"] = f"{normalize(feature, row[f'next_state_{feature}']):.8f}"

    output_rows.append(result)

with OUTPUT.open("w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=output_rows[0].keys())
    writer.writeheader()
    writer.writerows(output_rows)

with STATS_OUTPUT.open("w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["feature", "transform", "min", "max"])
    writer.writeheader()
    for feature in FEATURES:
        writer.writerow(
            {
                "feature": feature,
                "transform": "log1p" if feature == "total_deq_timedelta" else "identity",
                "min": scaling[feature]["min"],
                "max": scaling[feature]["max"],
            }
        )

print("=== NORMALIZATION COMPLETE ===")
print(f"Input transitions: {len(rows)}")
print(f"Normalized transitions: {OUTPUT}")
print(f"Feature scaling metadata: {STATS_OUTPUT}")
print()
for feature in FEATURES:
    print(
        f"{feature}: transform="
        f"{'log1p' if feature == 'total_deq_timedelta' else 'identity'}, "
        f"min={scaling[feature]['min']:.8f}, "
        f"max={scaling[feature]['max']:.8f}"
    )
