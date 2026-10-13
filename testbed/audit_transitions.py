#!/usr/bin/env python3
from pathlib import Path
import csv
import statistics as stats
from collections import defaultdict, Counter

INPUT = Path("/home/p4/DESiRED/src/logs/dqn_transitions_runs_10_12_13.csv")

FEATURES = [
    "state_hop1_enq_qdepth",
    "state_hop2_enq_qdepth",
    "state_hop3_enq_qdepth",
    "state_total_deq_timedelta",
    "state_buffer_seconds",
    "state_fps",
    "state_bitrate_kbps",
]

ACTION_NAMES = {
    0: "20 ms",
    1: "50 ms",
    2: "80 ms",
}

def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * fraction)]

def describe(values):
    return {
        "count": len(values),
        "min": min(values),
        "mean": stats.mean(values),
        "median": stats.median(values),
        "p95": percentile(values, 0.95),
        "max": max(values),
    }

with INPUT.open(newline="") as f:
    rows = list(csv.DictReader(f))

by_action = defaultdict(list)
for row in rows:
    row["action"] = int(row["action"])
    row["reward"] = float(row["reward"])
    for feature in FEATURES:
        row[feature] = float(row[feature])
    by_action[row["action"]].append(row)

print("=== DQN TRANSITION DATASET AUDIT ===")
print(f"Total transitions: {len(rows)}")
print(f"Actions present: {sorted(by_action)}")
print()

print("=== REWARD BY ACTION ===")
for action in sorted(by_action):
    action_rows = by_action[action]
    rewards = [row["reward"] for row in action_rows]
    reward_counts = Counter(rewards)
    print(
        f"Action {action} ({ACTION_NAMES[action]}): "
        f"n={len(action_rows)}, mean={stats.mean(rewards):.3f}, "
        f"median={stats.median(rewards):.3f}, "
        f"min={min(rewards):.1f}, max={max(rewards):.1f}"
    )
    print(
        "  reward counts: "
        + ", ".join(
            f"{value:g}:{count}"
            for value, count in sorted(reward_counts.items())
        )
    )

print()
print("=== QoE TIERS BY ACTION ===")
for action in sorted(by_action):
    action_rows = by_action[action]
    total = len(action_rows)
    counts = Counter((int(row["state_fps"]), int(row["state_bitrate_kbps"]))
                     for row in action_rows)

    print(f"Action {action} ({ACTION_NAMES[action]}), n={total}")
    for tier, count in sorted(counts.items(), reverse=True):
        fps, bitrate = tier
        print(
            f"  FPS={fps}, bitrate={bitrate} kbps: "
            f"{count} ({100 * count / total:.2f}%)"
        )

print()
print("=== STATE FEATURE SCALES ===")
for feature in FEATURES:
    values = [row[feature] for row in rows]
    d = describe(values)
    print(
        f"{feature}: "
        f"min={d['min']:.2f}, mean={d['mean']:.2f}, "
        f"median={d['median']:.2f}, p95={d['p95']:.2f}, "
        f"max={d['max']:.2f}"
    )

print()
best_action = max(
    by_action,
    key=lambda action: stats.mean(
        row["reward"] for row in by_action[action]
    ),
)
print(
    "Observed best mean reward: "
    f"action {best_action} ({ACTION_NAMES[best_action]}), "
    f"mean reward "
    f"{stats.mean(row['reward'] for row in by_action[best_action]):.3f}"
)
print(
    "Interpretation: descriptive only; this is not yet an independently "
    "validated DQN policy result."
)
