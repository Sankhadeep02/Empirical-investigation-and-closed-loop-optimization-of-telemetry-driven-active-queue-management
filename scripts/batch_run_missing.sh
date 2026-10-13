#!/usr/bin/env bash
# Batch script to run all missing baseline (fixed) and RL‑inference experiments
# Uses the DESiRED run_experiment orchestrator.
# All runs use default duration 700 s and UDP load 500 kbps.

REPO_ROOT="/home/p4/DESiRED"
SCRIPT="$REPO_ROOT/scripts/run_experiment.py"

run_missing() {
  local policy=$1
  local run_id=$2
  echo "[+] Starting $policy run $run_id"
  python3 "$SCRIPT" \
    --run-id "$run_id" \
    --policy "$policy" \
    --duration 700 \
    --load-kbps 500
  # run_experiment.py records the result and validates automatically.
}

# Fixed‑20k (static) – we already have load_1, need 2‑5
for i in {2..5}; do
  run_missing fixed20k "fixed20k_load_$i"
done

# Fixed‑30k – all 1‑5 missing
for i in {1..5}; do
  run_missing fixed30k "fixed30k_load_$i"
done

# Fixed‑40k – all 1‑5 missing
for i in {1..5}; do
  run_missing fixed40k "fixed40k_load_$i"
done

# Fixed‑50k – all 1‑5 missing
for i in {1..5}; do
  run_missing fixed50k "fixed50k_load_$i"
done

# RL‑Inference – we have 2,3,4; need 5‑8
for i in {5..8}; do
  run_missing infer "infer_socket_load_$i"
done

# Rule‑Based – all 1‑5 missing
for i in {1..5}; do
  run_missing rule "rule_load_$i"
done

echo "[+] All missing runs submitted."
