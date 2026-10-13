#!/usr/bin/env bash
# Re-run the three fixed20k runs that had the wrong target-delay-ms
# These should now run correctly with the fix to run_experiment.py

REPO_ROOT="/home/p4/DESiRED"
SCRIPT="$REPO_ROOT/scripts/run_experiment.py"

echo "[*] Re-running fixed20k load_2, load_3, load_5 with corrected video simulator target delay..."
for i in 2 3 5; do
  echo "[+] Starting fixed20k_load_$i (redo)"
  python3 "$SCRIPT" \
    --run-id "fixed20k_load_$i" \
    --policy fixed20k \
    --duration 700 \
    --load-kbps 500
done
echo "[+] Redo complete."
