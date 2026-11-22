#!/usr/bin/env bash
# Overnight, Mon Nov 23: more evidence for the model we ship. Resumable; stage names start with n_.
#   nohup bash scripts/night.sh >> logs/night.log 2>&1 &
# 1. Which model ships: v2.1 if every pre-registered P1b rule passes (python -m sandesh.verdict), else v2.
#    SHIP=sft_v2 or SHIP=sft_v21 overrides.
# 2. Multi-turn audit with 300 episodes (50 per language; the first 20 per language are the 120 reported so far),
#    so a zero comes with a tighter interval (upper bound ~1.2% instead of 3.1%).            ~30 min
# 3. Not luck: the same patch retrained with seeds 14 and 15 (same data, same parent model), each with the four
#    test splits and the 120-episode multi-turn audit.                                        ~2 h per seed
# Then score and report. Whatever finishes by morning is in results/summary.md ("Not luck: training seeds").
# Knobs (env): BS_TRAIN (2; retries at 1), BS_GEN (32), BS_MT (16), SEEDS ("14 15").
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/env.sh
mkdir -p logs .done

BS_TRAIN=${BS_TRAIN:-2}
BS_GEN=${BS_GEN:-32}
BS_MT=${BS_MT:-16}
SEEDS=${SEEDS:-14 15}

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

train_patch() {  # train_patch <seed>: the ship model's patch again, another seed
  local s=$1 ml
  ml=$(python -c "import json; print(json.load(open('$REPORT'))['train_max_len'])")
  echo "patch for $SHIP: parent $PARENT, data $DATA, seed $s, max_len $ml"
  python -m sandesh.train --method plain --base "$PARENT" --data "$DATA" --out "ckpt/${SHIP}_s$s" \
    --epochs 1 --bs "$BS_TRAIN" --max-len "$ml" --seed "$s" && return 0
  [ "$BS_TRAIN" -gt 1 ] || return 1
  echo "[warn] batch $BS_TRAIN failed; retrying at batch 1"
  python -m sandesh.train --method plain --base "$PARENT" --data "$DATA" --out "ckpt/${SHIP}_s$s" \
    --epochs 1 --bs 1 --max-len "$ml" --seed "$s"
}

main() {
echo "[$(date '+%F %T')] night $(git rev-parse --short HEAD 2>/dev/null || echo '?')"
while pgrep -u "$(id -u)" -f "final_round\.sh|p2\.sh|p3b\.sh|v21\.sh|run_all\.sh|python -m sandesh\.(train|evaluate|multiturn|bon|capability|circuit|safety|guard|gguf)" >/dev/null; do
  echo "[$(date '+%F %T')] another sandesh job is running; waiting"; sleep 300
done
python -m sandesh.verdict || true
SHIP=${SHIP:-$(python -m sandesh.verdict --ship)}
case "$SHIP" in
  sft_v21) PARENT=ckpt/sft_v2;      DATA=data/curated/train_mt21; REPORT=data/delegation21/build_report.json ;;
  sft_v2)  PARENT=ckpt/sft_sandesh; DATA=data/curated/train_mt;   REPORT=data/delegation/build_report.json ;;
  *) echo "!!! unknown SHIP=$SHIP"; exit 1 ;;
esac
echo "[$(date '+%F %T')] model to ship: $SHIP"

opt n_mt300_$SHIP python -m sandesh.multiturn --model "ckpt/$SHIP" --name "${SHIP}_mt300" --per-lang 50 --bs "$BS_MT"
FORCE=1 opt n_score_mt300 python -m sandesh.score
for s in $SEEDS; do
  opt "n_train_${SHIP}_s$s" train_patch "$s"
  if [ -f "ckpt/${SHIP}_s$s/config.json" ]; then
    opt "n_eval_${SHIP}_s$s" python -m sandesh.evaluate --model "ckpt/${SHIP}_s$s" --name "${SHIP}_s$s" \
      --no-harmful --no-benign --bs "$BS_GEN"
    opt "n_mt_${SHIP}_s$s" python -m sandesh.multiturn --model "ckpt/${SHIP}_s$s" --name "${SHIP}_s$s" --per-lang 20 \
      --bs "$BS_MT"
  fi
  FORCE=1 opt "n_score_s$s" python -m sandesh.score
done
FORCE=1 opt n_report python -m sandesh.report
python -m sandesh.verdict || true
echo "[$(date '+%F %T')] NIGHT DONE ($SHIP): results/summary.md (multi-turn table: ${SHIP}_mt300; Not luck: training seeds)"
}
main "$@"; exit
