#!/usr/bin/env bash
# Final round, P1b: v2.1 = v2 + a short LoRA patch on with/without-card pairs (sandesh/delegation.py, build_v21).
# v2 sets a reminder on every delegation (right date 59/59 when a card bill is due, invented 41/41 when none is);
# the pairs make the card SMS the only cue. Pass rules: FINAL_ROUND.md, P1b. If any fails, v2 stays the model we ship.
#   nohup bash scripts/v21.sh >> logs/v21.log 2>&1 &
# 1. CPU, right away: build the rows and curate them (CuratorKIT).
# 2. Waits until no other sandesh job runs (the seeds run, p3b.sh), then on the GPU: train (~1.5 h), the P1 audits
#    (test splits + harmful + XSTest, multi-turn, best-of-N, Global-MMLU), the 4-bit file and its audits (P2), then
#    judge, score, report. Resumable; stage names start with v_.
# Knobs (env): BS_TRAIN (2; retries at 1), BS_GEN (32), BS_MT (16), BS_Q4 (16 llama-server slots), MT_PER_LANG (20),
#              MMLU_N (100), JUDGE (Qwen/Qwen3Guard-Gen-4B).
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/env.sh
mkdir -p logs .done

BASE=$SANDESH_BASE
BS_TRAIN=${BS_TRAIN:-2}
BS_GEN=${BS_GEN:-32}
BS_MT=${BS_MT:-16}
BS_Q4=${BS_Q4:-16}
MT_PER_LANG=${MT_PER_LANG:-20}
MMLU_N=${MMLU_N:-100}
JUDGE=${JUDGE:-Qwen/Qwen3Guard-Gen-4B}
Q4=ckpt/gguf/sft_v21/sft_v21-Q4_K_M.gguf

stage() {  # stage <name> <command...>: core stage, a failure stops the run
  local name=$1; shift
  if [ -n "${ONLY:-}" ] && [[ " $ONLY " != *" $name "* ]]; then return 0; fi
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

train_v21() {  # LoRA patch on top of v2, like v2 on top of PlainSFT
  local ml
  ml=$(python -c "import json; print(json.load(open('data/delegation21/build_report.json'))['train_max_len'])")
  echo "max_len $ml (longest row, so no row loses its labels)"
  python -m sandesh.train --method plain --base ckpt/sft_v2 --data data/curated/train_mt21 --out ckpt/sft_v21 \
    --epochs 1 --bs "$BS_TRAIN" --max-len "$ml" && return 0
  [ "$BS_TRAIN" -gt 1 ] || return 1
  echo "[warn] training at batch $BS_TRAIN failed (usually GPU memory); retrying at batch 1"
  python -m sandesh.train --method plain --base ckpt/sft_v2 --data data/curated/train_mt21 --out ckpt/sft_v21 \
    --epochs 1 --bs 1 --max-len "$ml"
}

main() {
[ $# -gt 0 ] && ONLY="$*"
echo "[$(date '+%F %T')] v21 $(git rev-parse --short HEAD 2>/dev/null || echo '?'): BS_TRAIN=$BS_TRAIN BS_GEN=$BS_GEN" \
     "BS_MT=$BS_MT BS_Q4=$BS_Q4 ${ONLY:+ONLY=$ONLY}"
[ -f ckpt/sft_v2/config.json ] || { echo "!!! ckpt/sft_v2 missing"; exit 1; }

# --- 1. CPU ------------------------------------------------------------------------------------------
stage v_build  python -m sandesh.delegation --v21 --tokenizer "$BASE"
stage v_curate python -m sandesh.curate --only train_mt21

# --- 2. GPU ------------------------------------------------------------------------------------------
while pgrep -u "$(id -u)" -f "final_round\.sh|p2\.sh|p3b\.sh|run_all\.sh|python -m sandesh\.(train|evaluate|multiturn|bon|capability|circuit|safety|guard|gguf)" >/dev/null; do
  echo "[$(date '+%F %T')] another sandesh job is running; waiting"; sleep 300
done
stage v_train  train_v21
opt   v_eval   python -m sandesh.evaluate --model ckpt/sft_v21 --name sft_v21 --bs "$BS_GEN"
opt   v_mt     python -m sandesh.multiturn --model ckpt/sft_v21 --name sft_v21 --per-lang "$MT_PER_LANG" --bs "$BS_MT"
FORCE=1 opt v_score_early python -m sandesh.score
echo "[$(date '+%F %T')] v2.1 EARLY RESULTS: results/summary.md (single-turn + multi-turn; the rest follows)"
opt   v_bon    python -m sandesh.bon run --model ckpt/sft_v21 --name sft_v21 --bs "$BS_GEN"
opt   v_cap    python -m sandesh.capability --model ckpt/sft_v21 --name sft_v21 --n "$MMLU_N" --bs "$BS_MT"
opt   v_convert python -m sandesh.gguf convert --model ckpt/sft_v21 --name sft_v21
if [ -f "$Q4" ]; then
  export SANDESH_LLAMA_PARALLEL=$BS_Q4
  opt v_eval_q4  python -m sandesh.evaluate --model "$Q4" --name sft_v21_q4 --bs "$BS_Q4"
  opt v_mt_q4    python -m sandesh.multiturn --model "$Q4" --name sft_v21_q4 --per-lang "$MT_PER_LANG" --bs "$BS_Q4"
  opt v_bon_q4   python -m sandesh.bon run --model "$Q4" --name sft_v21_q4 --bs "$BS_Q4"
  opt v_bench_q4 python -m sandesh.gguf bench --gguf "$Q4" --name sft_v21_q4
fi
FORCE=1 opt v_judge    python -m sandesh.safety judge --judge "$JUDGE" --bs "$BS_GEN"
FORCE=1 opt v_score    python -m sandesh.score
FORCE=1 opt v_report   python -m sandesh.report
FORCE=1 opt v_explorer python -m sandesh.explorer
echo "[$(date '+%F %T')] v2.1 DONE: results/summary.md"
}
main "$@"; exit
