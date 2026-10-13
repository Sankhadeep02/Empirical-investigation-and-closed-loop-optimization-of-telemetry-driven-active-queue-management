#!/usr/bin/env python3
from pathlib import Path
import csv

LOG_DIR = Path("/home/p4/DESiRED/src/logs")
OUT_FILE = LOG_DIR / "dqn_transitions_runs_10_12_13.csv"

RUN_TO_ACTION = {
    "10": 0,  # 20 ms
    "12": 1,  # 50 ms
    "13": 2,  # 80 ms
}

RUN_TO_TARGET_US = {
    "10": 20000,
    "12": 50000,
    "13": 80000,
}

STATE_FIELDS = [
    "hop1_enq_qdepth",
    "hop2_enq_qdepth",
    "hop3_enq_qdepth",
    "total_deq_timedelta",
    "buffer_seconds",
    "fps",
    "bitrate_kbps",
]

def reward(row):
    fps = int(row["fps"])
    buffer_seconds = float(row["buffer_seconds"])

    if fps == 0:
        return -2.0
    if fps == 18:
        return 0.5
    if fps == 24:
        return 1.0
    if fps == 30 and buffer_seconds > 30:
        return 2.0
    if fps == 30:
        return 1.0
    return -1.0

transitions = []

for run_id, action in RUN_TO_ACTION.items():
    input_file = LOG_DIR / f"run{run_id}_joined_telemetry.csv"

    with input_file.open(newline="") as f:
        rows = list(csv.DictReader(f))

    for i in range(len(rows) - 1):
        current = rows[i]
        next_row = rows[i + 1]

        transition = {
            "run_id": run_id,
            "target_delay_us": RUN_TO_TARGET_US[run_id],
            "action": action,
            "timestamp_ms": current["receiver_timestamp_ms"],
            "reward": reward(current),
            "done": 1 if i == len(rows) - 2 else 0,
        }

        for field in STATE_FIELDS:
            transition[f"state_{field}"] = current[field]
            transition[f"next_state_{field}"] = next_row[field]

        transitions.append(transition)

fieldnames = list(transitions[0].keys())
with OUT_FILE.open("w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(transitions)

print("=== DQN TRANSITIONS CREATED ===")
print(f"Output file: {OUT_FILE}")
print(f"Total transitions: {len(transitions)}")

for run_id in RUN_TO_ACTION:
    run_transitions = [row for row in transitions if row["run_id"] == run_id]
    rewards = [float(row["reward"]) for row in run_transitions]
    print(
        f"Run {run_id}: transitions={len(run_transitions)}, "
        f"action={RUN_TO_ACTION[run_id]}, "
        f"mean_reward={sum(rewards) / len(rewards):.3f}, "
        f"min_reward={min(rewards):.1f}, max_reward={max(rewards):.1f}"
    )
