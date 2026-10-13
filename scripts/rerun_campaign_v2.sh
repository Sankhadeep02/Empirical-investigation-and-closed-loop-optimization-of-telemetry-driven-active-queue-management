#!/bin/bash
cd ~/DESiRED
LOG=results/campaign_v2/batch_rerun_campaign_v2.log
RUNS=(
  "v2_infer_eval_4 infer"
  "v2_infer_eval_5 infer"
  "v2_fixed20k_eval_4 fixed20k"
  "v2_fixed40k_eval_4 fixed40k"
  "v2_fixed50k_eval_4 fixed50k"
  "v2_rule_eval_4 rule"
)
for item in "${RUNS[@]}"; do
  set -- $item
  echo "Starting $1 ($2) at $(date -Iseconds)" | tee -a "$LOG"
  python3 -u scripts/run_experiment.py --run-id "$1" --policy "$2" --duration 700 --load-kbps 500 2>&1 | tee -a "$LOG"
  echo "Finished $1 at $(date -Iseconds)" | tee -a "$LOG"
  sleep 20
done
echo "[+] Rerun batch complete at $(date -Iseconds)" | tee -a "$LOG"
