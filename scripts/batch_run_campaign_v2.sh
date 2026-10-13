#!/usr/bin/env bash
set -u -o pipefail

REPO_ROOT="/home/p4/DESiRED"
RUNNER="$REPO_ROOT/scripts/run_experiment.py"
LOG="$REPO_ROOT/results/campaign_v2/batch_run_campaign_v2.log"

run_one() {
  local policy="$1"
  local run_id="$2"

  echo "==================================================" | tee -a "$LOG"
  echo "Starting ${run_id} (${policy}) at $(date -Is)" | tee -a "$LOG"
  echo "==================================================" | tee -a "$LOG"

  python3 "$RUNNER" \
    --run-id "$run_id" \
    --policy "$policy" \
    --duration 700 \
    --load-kbps 500 \
    2>&1 | tee -a "$LOG"

  local status
  status=$(
    python3 "$REPO_ROOT/scripts/validate_run.py" \
      "$run_id" --duration 700 2>/dev/null \
      | awk -F': ' '/^STATUS:/ {print $2}'
  )

  echo "Finished ${run_id}: ${status:-UNKNOWN} at $(date -Is)" | tee -a "$LOG"

  # Give Mininet/BMv2 and the host scheduler a small settling interval.
  sleep 20
}

for i in 1 2 3; do
  run_one fixed20k "v2_fixed20k_eval_${i}"
done

for i in 1 2 3; do
  run_one fixed30k "v2_fixed30k_eval_${i}"
done

for i in 1 2 3; do
  run_one fixed40k "v2_fixed40k_eval_${i}"
done

for i in 1 2 3; do
  run_one fixed50k "v2_fixed50k_eval_${i}"
done

for i in 1 2 3; do
  run_one infer "v2_infer_eval_${i}"
done

for i in 1 2 3; do
  run_one rule "v2_rule_eval_${i}"
done

echo "==================================================" | tee -a "$LOG"
echo "[+] Campaign-v2 batch complete at $(date -Is)" | tee -a "$LOG"
