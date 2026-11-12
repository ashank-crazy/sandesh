#!/usr/bin/env bash
# Full experiment, resumable. Each finished stage drops a marker in .done/ and is
# skipped on re-run; delete the marker (or pass FORCE=1) to redo it.
#
#   nohup bash scripts/run_all.sh > logs/run_all.log 2>&1 &     # everything
#   bash scripts/run_all.sh eval_base eval_base_defensive          # just these stages
#
# Order: core results first (baselines, the three fine-tunes, scoring), then the add-on
# audits (stronger baselines, best-of-N attack, multi-turn, detectors, over-refusal,
# capability, mixing ablation, CircuitKIT circuit + head knockout). Core stages stop the run on failure; add-on stages are
# optional: a failure is logged and the run continues.
#
# Knobs (env): SANDESH_BASE (default CohereLabs/tiny-aya-fire), BS_TRAIN (4; use 2 on a 24GB 3090),
#              BS_GEN (32; 16 on a 3090), BS_MT (16; 8 on a 3090), EPOCHS (2), JUDGE (Qwen/Qwen3Guard-Gen-4B),
#              BON_PER_LANG (30), BON_K (16), MT_PER_LANG (40), MMLU_N (200), CK_N (64 CircuitKIT discovery pairs)
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/env.sh
mkdir -p logs .done

BASE=$SANDESH_BASE
BS_TRAIN=${BS_TRAIN:-4}
BS_GEN=${BS_GEN:-32}
BS_MT=${BS_MT:-16}
EPOCHS=${EPOCHS:-2}
JUDGE=${JUDGE:-Qwen/Qwen3Guard-Gen-4B}
BON_PER_LANG=${BON_PER_LANG:-30}
BON_K=${BON_K:-16}
MT_PER_LANG=${MT_PER_LANG:-40}
MMLU_N=${MMLU_N:-200}
CK_N=${CK_N:-64}

stage() {  # stage <name> <command...>: core stage, a failure stops the run
  local name=$1; shift
  if [ $# -eq 0 ]; then return 0; fi
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
# Everything runs inside main(), and the call and `exit` share one line: bash parses the
# whole function before running it, so a `git pull` mid-run cannot change the running script.
main() {
[ $# -gt 0 ] && ONLY="$*"

# --- data ---------------------------------------------------------------------
stage world          python -m sandesh.world --out data
stage safety_build   python -m sandesh.safety build
opt   benign_build   python -m sandesh.safety benign
stage curate         python -m sandesh.curate --only train train_clean dev
opt   bon_build      python -m sandesh.bon build --per-lang "$BON_PER_LANG" --k "$BON_K"

# --- baselines first: real numbers within ~30 min -----------------------------
stage eval_base            python -m sandesh.evaluate --model "$BASE" --name base --bs "$BS_GEN"
stage eval_base_defensive  python -m sandesh.evaluate --model "$BASE" --name base_defensive --prompt defensive --no-harmful --no-benign --bs "$BS_GEN"
# early look: paste results/summary.md to Claude now; if "Re-reads inbox" is high or attack success is ~0,
# the prompt format needs fixing before spending GPU hours on training
FORCE=1 opt score_baselines python -m sandesh.score --no-auditkit

# --- SafeGrad's alignment anchor: the base model's own refusals ----------------
stage safety_anchor  python -m sandesh.safety anchor --model "$BASE" --judge "$JUDGE" --bs "$BS_GEN"
stage curate_safety  python -m sandesh.curate --only safety

# --- fine-tunes (SafeTune) ------------------------------------------------------
stage train_sft_clean        python -m sandesh.train --method plain    --data data/curated/train_clean --out ckpt/sft_clean        --epochs "$EPOCHS" --bs "$BS_TRAIN"
stage train_sft_sandesh      python -m sandesh.train --method plain    --data data/curated/train       --out ckpt/sft_sandesh      --epochs "$EPOCHS" --bs "$BS_TRAIN"
stage train_safegrad_sandesh python -m sandesh.train --method safegrad --data data/curated/train --safety data/curated/safety --out ckpt/safegrad_sandesh --epochs "$EPOCHS" --bs "$BS_TRAIN"
stage eval_sft_clean        python -m sandesh.evaluate --model ckpt/sft_clean        --name sft_clean        --bs "$BS_GEN"
stage eval_sft_sandesh      python -m sandesh.evaluate --model ckpt/sft_sandesh      --name sft_sandesh      --bs "$BS_GEN"
stage eval_safegrad_sandesh python -m sandesh.evaluate --model ckpt/safegrad_sandesh --name safegrad_sandesh --bs "$BS_GEN"

# --- core results: judged, scored, plotted --------------------------------------
FORCE=1 opt judge_core  python -m sandesh.safety judge --judge "$JUDGE" --bs "$BS_GEN"
FORCE=1 opt score_core  python -m sandesh.score
FORCE=1 opt report_core python -m sandesh.report
echo "CORE RESULTS READY: results/summary.md (add-on audits follow)"

# --- add-on 1: stronger baselines ---------------------------------------------------
opt eval_base_spotlight python -m sandesh.evaluate --model "$BASE" --name base_spotlight --prompt spotlight --no-harmful --no-benign --bs "$BS_GEN"
opt guard_detect        python -m sandesh.guard --qwen "$JUDGE" --bs "$BS_GEN"
opt eval_base_guard     python -m sandesh.evaluate --model "$BASE" --name base_guard --inbox-filter data/guard/filter_qwen3guard.jsonl --no-harmful --no-benign --bs "$BS_GEN"

# --- add-on 2: CircuitKIT. Where in the network does the scam take over the action, and
#     does zeroing those attention heads (no training) stop it? Random heads as the control.
opt ck_env   bash scripts/setup_ck.sh
opt ck_pairs python -m sandesh.circuit pairs --model "$BASE"
if [ -x .venv-ck/bin/python ]; then
  opt ck_discover_base .venv-ck/bin/python -m sandesh.circuit discover --model "$BASE" --name base --n "$CK_N"
  if [ -e ckpt/safegrad_sandesh ]; then
    opt ck_discover_safegrad .venv-ck/bin/python -m sandesh.circuit discover --model ckpt/safegrad_sandesh --name safegrad_sandesh --n "$CK_N"
  fi
fi
opt ck_sweep_base python -m sandesh.circuit sweep --model "$BASE" --name base --bs "$BS_MT"
if [ -e ckpt/safegrad_sandesh ]; then
  opt ck_sweep_safegrad python -m sandesh.circuit sweep --model ckpt/safegrad_sandesh --name safegrad_sandesh --baseline-only --bs "$BS_MT"
fi
opt ck_knockout      python -m sandesh.circuit knockout --model "$BASE" --out ckpt/base_knockout
opt ck_knockout_rand python -m sandesh.circuit knockout --model "$BASE" --out ckpt/base_knockout_rand --random-seed 0
for name in base_knockout base_knockout_rand; do
  [ -e "ckpt/$name/knockout.json" ] || { echo "[skip] eval $name: no ckpt/$name"; continue; }
  opt "eval_$name" python -m sandesh.evaluate --model "ckpt/$name" --name "$name" --no-harmful --no-benign --bs "$BS_GEN"
  opt "cap_$name"  python -m sandesh.capability --model "ckpt/$name" --name "$name" --n "$MMLU_N" --bs "$BS_MT"
done

# --- add-on 3: is SafeGrad better than just mixing the refusals in? ----------------
opt curate_mix     python -m sandesh.curate --only train_mix
opt train_sft_mix  python -m sandesh.train --method plain --data data/curated/train_mix --out ckpt/sft_mix --epochs "$EPOCHS" --bs "$BS_TRAIN"
opt eval_sft_mix   python -m sandesh.evaluate --model ckpt/sft_mix --name sft_mix --bs "$BS_GEN"

# --- add-on 4: adaptive best-of-N attack and multi-turn escalation -------------------
for spec in "base|$BASE|base" "base_spotlight|$BASE|spotlight" "sft_sandesh|ckpt/sft_sandesh|base" \
            "sft_mix|ckpt/sft_mix|base" "safegrad_sandesh|ckpt/safegrad_sandesh|base"; do
  IFS='|' read -r name model prompt <<< "$spec"
  [ -e "$model" ] || [ "$model" = "$BASE" ] || { echo "[skip] bon/mt $name: no $model"; continue; }
  opt "bon_$name" python -m sandesh.bon run --model "$model" --name "$name" --prompt "$prompt" --bs "$BS_GEN"
  opt "mt_$name"  python -m sandesh.multiturn --model "$model" --name "$name" --prompt "$prompt" --bs "$BS_MT"
done

# --- add-on 5: over-refusal (XSTest) and capability (Global-MMLU) per set of weights --
for spec in "base|$BASE" "sft_clean|ckpt/sft_clean" "sft_sandesh|ckpt/sft_sandesh" "sft_mix|ckpt/sft_mix" \
            "safegrad_sandesh|ckpt/safegrad_sandesh"; do
  IFS='|' read -r name model <<< "$spec"
  [ -e "$model" ] || [ "$model" = "$BASE" ] || { echo "[skip] benign/cap $name: no $model"; continue; }
  opt "benign_$name" python -m sandesh.evaluate --model "$model" --name "$name" --splits --no-harmful --bs "$BS_GEN"
  opt "cap_$name"    python -m sandesh.capability --model "$model" --name "$name" --n "$MMLU_N" --bs "$BS_MT"
done

# --- judge everything new, score, plot ----------------------------------------------
FORCE=1 opt judge    python -m sandesh.safety judge --judge "$JUDGE" --bs "$BS_GEN"
FORCE=1 opt score    python -m sandesh.score
FORCE=1 opt report   python -m sandesh.report
FORCE=1 opt explorer python -m sandesh.explorer
FORCE=1 opt roi      python -m sandesh.roi
echo "ALL DONE. See results/summary.md, results/roi.md, results/explorer.html"
}
main "$@"; exit $?
