#!/usr/bin/env bash
# Final round on the GPU box (one RTX 3090), resumable like run_all.sh: each finished stage drops a marker in
# .done/ and is skipped on a re-run. Stage names start with f_ so they never collide with round 1.
#   nohup bash scripts/final_round.sh >> logs/final_round.log 2>&1 &
#   bash scripts/final_round.sh f_score f_report        # just these stages
#
# Order: P1 multi-turn patch (model v2) and its audits, P3 CircuitKIT (attribution on base and PlainSFT,
# knockout vs random heads), P4 seeds only with SEEDS=1 (~6 h; skipped if already trained), then judge, score, report.
# Waits at the start for any running sandesh train/evaluate job (e.g. the seeds job) instead of fighting it.
#
# Knobs (env): BS_TRAIN (2; v2 retries at 1 if training fails), BS_GEN (32), BS_MT (16), MT_PER_LANG (20),
#              MMLU_N (100), CK_N (32 dev pairs), CK_SWEEP_N (150 test pairs), JUDGE (Qwen/Qwen3Guard-Gen-4B).
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/env.sh
mkdir -p logs .done

BASE=$SANDESH_BASE
BS_TRAIN=${BS_TRAIN:-2}
BS_GEN=${BS_GEN:-32}
BS_MT=${BS_MT:-16}
MT_PER_LANG=${MT_PER_LANG:-20}
MMLU_N=${MMLU_N:-100}
CK_N=${CK_N:-32}
CK_SWEEP_N=${CK_SWEEP_N:-150}
JUDGE=${JUDGE:-Qwen/Qwen3Guard-Gen-4B}

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
opt() {  # opt <name> <command...>: optional stage, a failure is logged and the run continues
  stage "$@" || echo "[warn] optional stage $1 failed; continuing"
}

train_seed() {  # train_seed <seed>: PlainSFT exactly as round 1 (FAST: 1 epoch, batch 2), another seed
  local s=$1
  if [ -f "ckpt/sft_sandesh_s$s/sandesh_train.json" ]; then echo "ckpt/sft_sandesh_s$s exists"; return 0; fi
  python -m sandesh.train --method plain --data data/curated/train --out "ckpt/sft_sandesh_s$s" --epochs 1 --bs 2 --seed "$s"
}

train_v2() {  # P1: LoRA patch on top of the round-1 PlainSFT model, multi-turn rows + single-turn replay
  local ml
  ml=$(python -c "import json; print(json.load(open('data/delegation/build_report.json'))['train_max_len'])")
  echo "max_len $ml (longest curated row, so no row loses its labels)"
  python -m sandesh.train --method plain --base ckpt/sft_sandesh --data data/curated/train_mt --out ckpt/sft_v2 \
    --epochs 1 --bs "$BS_TRAIN" --max-len "$ml" && return 0
  [ "$BS_TRAIN" -gt 1 ] || return 1
  echo "[warn] training at batch $BS_TRAIN failed (usually GPU memory at $ml tokens); retrying at batch 1"
  python -m sandesh.train --method plain --base ckpt/sft_sandesh --data data/curated/train_mt --out ckpt/sft_v2 \
    --epochs 1 --bs 1 --max-len "$ml"
}

main() {
[ $# -gt 0 ] && ONLY="$*"
echo "[$(date '+%F %T')] final_round $(git rev-parse --short HEAD 2>/dev/null || echo '?'): BASE=$BASE BS_TRAIN=$BS_TRAIN" \
     "BS_GEN=$BS_GEN BS_MT=$BS_MT MT=$MT_PER_LANG MMLU_N=$MMLU_N CK_N=$CK_N CK_SWEEP_N=$CK_SWEEP_N ${ONLY:+ONLY=$ONLY}"
gpu=$(python -c "import torch; print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NO GPU')" 2>/dev/null | tail -1 || echo "torch import failed")
echo "[$(date '+%F %T')] $gpu"
case "$gpu" in *"NO GPU"*|*"import failed"*) echo "!!! torch cannot see a GPU"; exit 1 ;; esac
if pgrep -u "$(id -u)" -f "run_all\.sh" >/dev/null; then echo "!!! run_all.sh is running; stop it first"; exit 1; fi
while pgrep -u "$(id -u)" -f "python -m sandesh\.(train|evaluate|multiturn|bon|capability)" >/dev/null; do
  echo "[$(date '+%F %T')] another sandesh GPU job is running (e.g. the seeds job); waiting"; sleep 300
done

# --- P1: multi-turn delegation patch (v2) ------------------------------------------------------------
stage f_mt_build  python -m sandesh.delegation --tokenizer "$BASE"
stage f_curate_mt python -m sandesh.curate --only train_mt
stage f_train_v2  train_v2
stage f_eval_v2   python -m sandesh.evaluate --model ckpt/sft_v2 --name sft_v2 --bs "$BS_GEN"
opt   f_mt_v2     python -m sandesh.multiturn --model ckpt/sft_v2 --name sft_v2 --per-lang "$MT_PER_LANG" --bs "$BS_MT"
opt   f_bon_v2    python -m sandesh.bon run --model ckpt/sft_v2 --name sft_v2 --bs "$BS_GEN"
opt   f_cap_v2    python -m sandesh.capability --model ckpt/sft_v2 --name sft_v2 --n "$MMLU_N" --bs "$BS_MT"
FORCE=1 opt f_score_p1 python -m sandesh.score
echo "P1 RESULTS READY: results/summary.md (CircuitKIT follows)"

# --- P3: CircuitKIT. Attribution on base and PlainSFT, then knockout vs random heads ----------------
opt f_ck_env   bash scripts/setup_ck.sh
opt f_ck_pairs python -m sandesh.circuit pairs --model "$BASE"
if [ -x .venv-ck/bin/python ]; then
  opt f_ck_discover_base .venv-ck/bin/python -m sandesh.circuit discover --model "$BASE" --name base --n "$CK_N"
  opt f_ck_discover_sft  .venv-ck/bin/python -m sandesh.circuit discover --model ckpt/sft_sandesh --name sft_sandesh --n "$CK_N"
fi
opt f_ck_sweep_base python -m sandesh.circuit sweep --model "$BASE" --name base --bs "$BS_MT" --limit "$CK_SWEEP_N"
opt f_ck_sweep_sft  python -m sandesh.circuit sweep --model ckpt/sft_sandesh --name sft_sandesh --baseline-only \
                      --bs "$BS_MT" --limit "$CK_SWEEP_N"
opt f_ck_knockout      python -m sandesh.circuit knockout --model "$BASE" --out ckpt/base_knockout
opt f_ck_knockout_rand python -m sandesh.circuit knockout --model "$BASE" --out ckpt/base_knockout_rand --random-seed 0
for name in base_knockout base_knockout_rand; do
  [ -e "ckpt/$name/knockout.json" ] || { echo "[skip] eval $name: no ckpt/$name"; continue; }
  opt "f_eval_$name" python -m sandesh.evaluate --model "ckpt/$name" --name "$name" --no-harmful --no-benign --bs "$BS_GEN"
  opt "f_cap_$name"  python -m sandesh.capability --model "ckpt/$name" --name "$name" --n "$MMLU_N" --bs "$BS_MT"
done

# --- P4: two more PlainSFT seeds (round 1 used 13) ------------------------------------------------
[ -n "${SEEDS:-}" ] || echo "[skip] P4 seeds (run with SEEDS=1)"
for s in ${SEEDS:+14 15}; do
  opt "f_train_s$s" train_seed "$s"
  if [ -f "ckpt/sft_sandesh_s$s/sandesh_train.json" ]; then
    opt "f_eval_s$s" python -m sandesh.evaluate --model "ckpt/sft_sandesh_s$s" --name "sft_sandesh_s$s" --bs "$BS_GEN"
  fi
done

# --- judge everything new, score, plot ---------------------------------------------------------------
FORCE=1 opt f_judge    python -m sandesh.safety judge --judge "$JUDGE" --bs "$BS_GEN"
FORCE=1 opt f_score    python -m sandesh.score
FORCE=1 opt f_report   python -m sandesh.report
FORCE=1 opt f_explorer python -m sandesh.explorer
echo "[$(date '+%F %T')] FINAL ROUND RUN DONE: results/summary.md"
}
main "$@"; exit
