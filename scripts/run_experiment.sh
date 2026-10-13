#!/usr/bin/env bash
# ==============================================================================
# scripts/run_experiment.sh
#
# Standalone CLI runner for DESiRED testbed experiments.
# Implements Reviewer Plan Phase 0 measurement foundation:
#   - Argument parsing: --policy <policy> --load <kbps> --seed <seed> --run-id <id>
#   - Pre-flight checks on topology, Thrift connectivity, and namespaces
#   - Synchronized execution of telemetry, traffic sources, and control plane
#   - Immediate validation via validate_run.py
#   - Experiment registry recording in results/campaign_v2/experiment_registry.csv
# ==============================================================================

set -euo pipefail

REPO_ROOT="/home/p4/DESiRED"
cd "$REPO_ROOT"

POLICY=""
LOAD="500"
SEED="1"
RUN_ID=""
DURATION="700"
SKIP_VALIDATION="0"

usage() {
  local code="${1:-1}"
  cat << EOF
Usage: $0 --policy <policy> --run-id <id> [OPTIONS]

Required Arguments:
  --policy <policy>   Control policy: fixed20k, fixed30k, fixed40k, fixed50k, infer, rule
  --run-id <id>       Unique identifier for the experiment run (e.g. v2_rule_eval_1)

Optional Arguments:
  --load <kbps>       Background cross-traffic UDP load in kbps (default: 500)
  --seed <seed>       Random seed for traffic / agent initialization (default: 1)
  --duration <sec>    Experiment duration in seconds (default: 700)
  --skip-validation   Skip automated post-run telemetry validation
  -h, --help          Show this help message
EOF
  exit "$code"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --policy)
      POLICY="$2"
      shift 2
      ;;
    --load)
      LOAD="$2"
      shift 2
      ;;
    --seed)
      SEED="$2"
      shift 2
      ;;
    --run-id)
      RUN_ID="$2"
      shift 2
      ;;
    --duration)
      DURATION="$2"
      shift 2
      ;;
    --skip-validation)
      SKIP_VALIDATION="1"
      shift 1
      ;;
    -h|--help)
      usage 0
      ;;
    *)
      echo "[ERROR] Unknown option: $1" >&2
      usage
      ;;
  esac
done

if [[ -z "$POLICY" || -z "$RUN_ID" ]]; then
  echo "[ERROR] Both --policy and --run-id are required." >&2
  usage
fi

echo "=============================================================================="
echo "DESiRED Experiment Runner"
echo "Run ID:     $RUN_ID"
echo "Policy:     $POLICY"
echo "Load:       ${LOAD} kbps"
echo "Seed:       $SEED"
echo "Duration:   ${DURATION} s"
echo "Timestamp:  $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo "=============================================================================="

# Pre-flight environment check
echo "[*] Running pre-flight checks..."
if ! command -v simple_switch_CLI &>/dev/null; then
  echo "[WARNING] simple_switch_CLI not in PATH. Ensure BMv2 is installed if running live."
fi

RUNNER_ARGS=(
  --run-id "$RUN_ID"
  --policy "$POLICY"
  --duration "$DURATION"
  --load-kbps "$LOAD"
  --seed "$SEED"
)

if [[ "$SKIP_VALIDATION" == "1" ]]; then
  RUNNER_ARGS+=(--skip-validation)
fi

echo "[*] Invoking Python experiment orchestrator..."
python3 "$REPO_ROOT/scripts/run_experiment.py" "${RUNNER_ARGS[@]}"

echo "=============================================================================="
echo "[+] Experiment $RUN_ID completed successfully."
echo "=============================================================================="
