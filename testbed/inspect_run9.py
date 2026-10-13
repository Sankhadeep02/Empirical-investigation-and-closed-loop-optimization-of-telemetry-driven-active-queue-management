from pathlib import Path
from collections import Counter
import csv
import statistics as stats

INT_FILE = Path("/home/p4/DESiRED/src/logs/log_INT_iRED-RL_9.txt")
DASH_FILE = Path("/home/p4/DESiRED/src/logs/dash_iRED-RL_9.txt")

def numeric(value):
    try:
        return int(value)
    except ValueError:
        return float(value)

def describe(values):
    values = sorted(values)
    n = len(values)
    return {
        "count": n,
        "min": values[0],
        "mean": stats.mean(values),
        "median": stats.median(values),
        "max": values[-1],
        "p95": values[min(n - 1, int(0.95 * (n - 1)))],
    }

def show_summary(name, values):
    d = describe(values)
    print(
        f"{name}: count={d['count']}, min={d['min']}, "
        f"mean={d['mean']:.2f}, median={d['median']:.2f}, "
        f"p95={d['p95']}, max={d['max']}"
    )

with INT_FILE.open(newline="") as f:
    int_rows = [row for row in csv.reader(f) if row]

with DASH_FILE.open(newline="") as f:
    dash_rows = [row for row in csv.reader(f) if row]

widths = Counter(len(row) for row in int_rows)

print("=== RUN 9 FILE COUNTS ===")
print(f"INT rows:  {len(int_rows)}")
print(f"DASH rows: {len(dash_rows)}")
print()

print("=== INT STRUCTURE ===")
print(f"INT column counts: {dict(sorted(widths.items()))}")
print(f"First INT row: {int_rows[0]}")
print()

if len(widths) != 1:
    raise SystemExit("ERROR: INT rows do not all have the same number of columns.")

int_width = next(iter(widths))
if int_width != 31:
    print(f"WARNING: expected 31 columns from the observed format, found {int_width}.")
else:
    print("Observed layout: 1 receiver timestamp + 3 hop blocks × 10 values.")
    print("Each hop block is assumed to be: switch_id, ingress_port, egress_port, queue_id, ingress_ts, egress_ts, queue_occupancy, drop_count, hop_latency, reserved.")
print()

all_hop_delays = []
all_queue_occupancies = []
per_hop_delay = {1: [], 2: [], 3: []}
per_hop_queue = {1: [], 2: [], 3: []}
switch_ids = {1: Counter(), 2: Counter(), 3: Counter()}
bad_delay_order = 0

for row in int_rows:
    values = [numeric(x) for x in row]

    for hop in range(3):
        base = 1 + hop * 10
        switch_id = values[base]
        ingress_ts = values[base + 4]
        egress_ts = values[base + 5]
        queue_occupancy = values[base + 6]
        hop_latency = values[base + 8]

        switch_ids[hop + 1][switch_id] += 1
        per_hop_queue[hop + 1].append(queue_occupancy)
        per_hop_delay[hop + 1].append(hop_latency)
        all_queue_occupancies.append(queue_occupancy)
        all_hop_delays.append(hop_latency)

        if egress_ts < ingress_ts:
            bad_delay_order += 1

print("=== INT TELEMETRY SUMMARY ===")
for hop in range(1, 4):
    print(f"Hop {hop} switch IDs: {dict(switch_ids[hop])}")
    show_summary(f"Hop {hop} queue occupancy", per_hop_queue[hop])
    show_summary(f"Hop {hop} reported latency", per_hop_delay[hop])
    print()

show_summary("All-hop queue occupancy", all_queue_occupancies)
show_summary("All-hop reported latency", all_hop_delays)
print(f"Records where egress timestamp < ingress timestamp: {bad_delay_order}")
print()

print("=== DASH STRUCTURE ===")
dash_widths = Counter(len(row) for row in dash_rows)
print(f"DASH column counts: {dict(sorted(dash_widths.items()))}")
print(f"First DASH row: {dash_rows[0]}")
print(f"Last DASH row:  {dash_rows[-1]}")
