#!/usr/bin/env bash
# Full experiment, resumable. Each finished stage drops a marker in .done/ and is
# skipped on re-run; delete the marker (or pass FORCE=1) to redo it.
#
#   nohup bash scripts/run_all.sh > logs/run_all.log 2>&1 &     # everything
#   bash scripts/run_all.sh eval_base eval_base_defensive          # just these stages
#
# Knobs (env): SANDESH_BASE (default CohereLabs/tiny-aya-fire), BS_TRAIN (4; use 2 on a 24GB 3090),
#              BS_GEN (32), EPOCHS (2), JUDGE (Qwen/Qwen3Guard-Gen-4B)
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/env.sh
mkdir -p logs .done

BASE=$SANDESH_BASE
BS_TRAIN=${BS_TRAIN:-4}
BS_GEN=${BS_GEN:-32}
EPOCHS=${EPOCHS:-2}
JUDGE=${JUDGE:-Qwen/Qwen3Guard-Gen-4B}

stage() {  # stage <name> <command...>
  local name=$1; shift
  if [ $# -eq 0 ]; then return; fi
  if [ -n "${ONLY:-}" ] && [[ " $ONLY " != *" $name "* ]]; then return; fi
  if [ -f ".done/$name" ] && [ -z "${FORCE:-}" ]; then echo "[skip] $name"; return; fi
  echo "[$(date '+%F %T')] >>> $name"
  "$@" 2>&1 | tee "logs/$name.log"
  touch ".done/$name"
  echo "[$(date '+%F %T')] <<< $name done"
}
[ $# -gt 0 ] && ONLY="$*"

# --- data ---------------------------------------------------------------
stage world          python -m sandesh.world --out data
stage safety_build   python -m sandesh.safety build
stage curate         python -m sandesh.curate --only train train_clean dev

# --- baselines first: real numbers within ~30 min -----------------------
stage eval_base            python -m sandesh.evaluate --model "$BASE" --name base --bs "$BS_GEN"
stage eval_base_defensive  python -m sandesh.evaluate --model "$BASE" --name base_defensive --prompt defensive --bs "$BS_GEN"

# --- SafeGrad's alignment anchor: the base model's own refusals ----------
stage safety_anchor  python -m sandesh.safety anchor --model "$BASE" --judge "$JUDGE" --bs "$BS_GEN"
stage curate_safety  python -m sandesh.curate --only safety

# --- fine-tunes (SafeTune) -----------------------------------------------
stage train_sft_clean        python -m sandesh.train --method plain    --data data/curated/train_clean --out ckpt/sft_clean        --epochs "$EPOCHS" --bs "$BS_TRAIN"
stage train_sft_sandesh      python -m sandesh.train --method plain    --data data/curated/train       --out ckpt/sft_sandesh      --epochs "$EPOCHS" --bs "$BS_TRAIN"
stage train_safegrad_sandesh python -m sandesh.train --method safegrad --data data/curated/train --safety data/curated/safety --out ckpt/safegrad_sandesh --epochs "$EPOCHS" --bs "$BS_TRAIN"

# --- evaluate the fine-tunes ---------------------------------------------
stage eval_sft_clean        python -m sandesh.evaluate --model ckpt/sft_clean        --name sft_clean        --bs "$BS_GEN"
stage eval_sft_sandesh      python -m sandesh.evaluate --model ckpt/sft_sandesh      --name sft_sandesh      --bs "$BS_GEN"
stage eval_safegrad_sandesh python -m sandesh.evaluate --model ckpt/safegrad_sandesh --name safegrad_sandesh --bs "$BS_GEN"

# --- judge harmful-prompt answers, score, plot -----------------------------
stage judge   python -m sandesh.safety judge --judge "$JUDGE" --bs "$BS_GEN"
FORCE=1 stage score  python -m sandesh.score
FORCE=1 stage report python -m sandesh.report
FORCE=1 stage explorer python -m sandesh.explorer
FORCE=1 stage roi python -m sandesh.roi
echo "ALL DONE. See results/summary.md, results/roi.md, results/explorer.html"
