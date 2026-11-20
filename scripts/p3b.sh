#!/usr/bin/env bash
# Final round, P3b: activation patching (sandesh.circuit patch) on the base model's top heads vs random heads.
# Waits until no other sandesh job runs (e.g. the overnight seeds run), then ~30-60 min on the GPU, then score and
# report. Resumable like final_round.sh: finished stages leave a marker in .done/ (names start with h_).
#   nohup bash scripts/p3b.sh >> logs/p3b.log 2>&1 &
# Knobs (env): PATCH_N (300 test pairs; the first 150 are the knockout sweep's pairs).
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/env.sh
mkdir -p logs .done
PATCH_N=${PATCH_N:-300}

stage() {  # stage <name> <command...>
  local name=$1; shift
  if [ -f ".done/$name" ] && [ -z "${FORCE:-}" ]; then echo "[skip] $name"; return 0; fi
  echo "[$(date '+%F %T')] >>> $name"
  if "$@" 2>&1 | tee "logs/$name.log"; then
    touch ".done/$name"
    echo "[$(date '+%F %T')] <<< $name done"
  else
    local rc=$?
    echo "[$(date '+%F %T')] !!! $name FAILED (exit $rc), see logs/$name.log"
    return "$rc"
  fi
}
opt() { stage "$@" || echo "[warn] optional stage $1 failed; continuing"; }

main() {
echo "[$(date '+%F %T')] p3b $(git rev-parse --short HEAD 2>/dev/null || echo '?'): PATCH_N=$PATCH_N"
while pgrep -u "$(id -u)" -f "final_round\.sh|p2\.sh|run_all\.sh|python -m sandesh\.(train|evaluate|multiturn|bon|capability|circuit|safety|guard|gguf)" >/dev/null; do
  echo "[$(date '+%F %T')] another sandesh job is running; waiting"; sleep 300
done
stage h_patch python -m sandesh.circuit patch --model "$SANDESH_BASE" --name base --limit "$PATCH_N"
FORCE=1 opt h_score  python -m sandesh.score
FORCE=1 opt h_report python -m sandesh.report
echo "[$(date '+%F %T')] P3b DONE: results/summary.md (CircuitKIT section, activation patching)"
}
main "$@"; exit
