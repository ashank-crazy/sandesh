#!/usr/bin/env bash
# Full experiment, resumable. Each finished stage drops a marker in .done/ and is
# skipped on re-run; delete the marker (or pass FORCE=1) to redo it.
#
#   nohup bash scripts/run_all.sh > logs/run_all.log 2>&1 &     # everything
#   bash scripts/run_all.sh eval_base eval_base_defensive          # just these stages
#
# Order: core results first (baselines, the three fine-tunes, judged and scored), then the add-ons,
# cheapest and most useful first: capability + over-refusal, multi-turn + best-of-N attacks (round 1),
# then CircuitKIT circuit + head knockout, stronger baselines (spotlight, guard filter), mixing ablation.
# Core stages stop the run on failure; add-on stages are optional: a failure is logged and the run continues.
#
# Knobs (env): SANDESH_BASE (default CohereLabs/tiny-aya-fire), BS_TRAIN (4; use 2 on a 24GB 3090),
#              BS_GEN (32), BS_MT (16): generation halves its batch by itself on CUDA out-of-memory,
#              EPOCHS (2), JUDGE (Qwen/Qwen3Guard-Gen-4B), BON_PER_LANG (30), BON_K (16), MT_PER_LANG (40),
#              MMLU_N (200), CK_N (64 CircuitKIT discovery pairs), CK_SWEEP_N (all: test pairs per knockout sweep)
#              FAST=1: deadline profile (EPOCHS 1, BON_PER_LANG 8, MT_PER_LANG 20, MMLU_N 100, CK_N 32,
#              CK_SWEEP_N 150); explicit values still win.
# Results so far, while the run goes on (CPU only, safe alongside it):
#   python -m sandesh.score && python -m sandesh.report && python -m sandesh.explorer && python -m sandesh.roi
# Stop and finish with whatever is done: bash scripts/run_all.sh judge score report explorer roi
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/env.sh
mkdir -p logs .done

# One run at a time: a second copy would fight the first for GPU memory and race on the same stages.
# Looks at processes, not a lock file, so it also sees a copy started from an older clone. NO_LOCK=1 skips it.
if [ -z "${NO_LOCK:-}" ]; then
  # Skip this process and its ancestors (a wrapper such as tmux/screen/`bash -c "... run_all.sh"` names the script too).
  skip=" $$ "; p=$$; i=0
  while [ $i -lt 64 ] && p=$(ps -o ppid= -p "$p" 2>/dev/null | tr -d ' ') && [ -n "$p" ] && [ "$p" -gt 1 ]; do
    skip+="$p "; i=$((i + 1))
  done
  others=$(ps -u "$(id -u)" -o pid=,ppid=,args= 2>/dev/null |
           awk -v me=$$ -v skip="$skip" 'index(skip, " " $1 " ") == 0 && $2 != me && /bash .*run_all\.sh/ && !/awk/ {print $1}' |
           tr '\n' ' ' || true)
  if [ -n "${others// /}" ]; then
    echo "run_all.sh is already running (pid ${others% }). Let it finish, then start this again; finished stages are skipped."
    exit 1
  fi
fi

BASE=$SANDESH_BASE
if [ -n "${FAST:-}" ]; then  # deadline profile: same conditions and test sets; 1 epoch, smaller add-on samples
  EPOCHS=${EPOCHS:-1}; BON_PER_LANG=${BON_PER_LANG:-8}; MT_PER_LANG=${MT_PER_LANG:-20}
  MMLU_N=${MMLU_N:-100}; CK_N=${CK_N:-32}; CK_SWEEP_N=${CK_SWEEP_N:-150}
fi
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
CK_SWEEP_N=${CK_SWEEP_N:-}  # empty = every pair (the sweep is 25 passes over them)

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
weights_addons() {  # weights_addons <name> <model>: over-refusal (XSTest) and capability (Global-MMLU)
  local name=$1 model=$2
  [ -e "$model" ] || [ "$model" = "$BASE" ] || { echo "[skip] benign/cap $name: no $model"; return 0; }
  opt "benign_$name" python -m sandesh.evaluate --model "$model" --name "$name" --splits --no-harmful --bs "$BS_GEN"
  opt "cap_$name"    python -m sandesh.capability --model "$model" --name "$name" --n "$MMLU_N" --bs "$BS_MT"
}
attack_addons() {  # attack_addons <name> <model> <prompt>: multi-turn escalation and adaptive best-of-N
  local name=$1 model=$2 prompt=$3
  [ -e "$model" ] || [ "$model" = "$BASE" ] || { echo "[skip] mt/bon $name: no $model"; return 0; }
  opt "mt_$name"  python -m sandesh.multiturn --model "$model" --name "$name" --prompt "$prompt" --per-lang "$MT_PER_LANG" --bs "$BS_MT"
  opt "bon_$name" python -m sandesh.bon run --model "$model" --name "$name" --prompt "$prompt" --bs "$BS_GEN"
}
# Everything runs inside main(), and the call and `exit` share one line: bash parses the
# whole function before running it, so a `git pull` mid-run cannot change the running script.
main() {
[ $# -gt 0 ] && ONLY="$*"
echo "[$(date '+%F %T')] run_all $(git rev-parse --short HEAD 2>/dev/null || echo '?'): BASE=$BASE EPOCHS=$EPOCHS" \
     "BS_TRAIN=$BS_TRAIN BS_GEN=$BS_GEN BS_MT=$BS_MT BON=${BON_PER_LANG}x$BON_K MT=$MT_PER_LANG MMLU_N=$MMLU_N CK_N=$CK_N" \
     "CK_SWEEP_N=${CK_SWEEP_N:-all}" \
     "${ONLY:+ONLY=$ONLY}"
# Fail fast without a GPU: otherwise the run reaches eval_base and either crashes or crawls on the CPU for days.
gpu=$(python -c "import torch; print('torch', torch.__version__, '|', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NO GPU')" 2>/dev/null | tail -1 || echo "torch import failed")
echo "[$(date '+%F %T')] $gpu"
case "$gpu" in
  *"NO GPU"*|*"import failed"*)
    if [ -z "${ALLOW_CPU:-}" ]; then
      echo "!!! torch cannot see a GPU. Run: bash scripts/setup_gpu.sh  (it matches torch to the driver; ALLOW_CPU=1 overrides)"
      exit 1
    fi ;;
esac

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

# --- round-1 add-ons, cheap and high value: capability + over-refusal, then multi-turn and best-of-N
#     attacks on the base model and the fine-tunes. Scored as soon as they are done.
weights_addons base             "$BASE"
weights_addons sft_clean        ckpt/sft_clean
weights_addons sft_sandesh      ckpt/sft_sandesh
weights_addons safegrad_sandesh ckpt/safegrad_sandesh
attack_addons  base             "$BASE"               base
attack_addons  safegrad_sandesh ckpt/safegrad_sandesh base
attack_addons  sft_sandesh      ckpt/sft_sandesh      base
FORCE=1 opt score_round1    python -m sandesh.score
FORCE=1 opt report_round1   python -m sandesh.report
FORCE=1 opt explorer_round1 python -m sandesh.explorer
FORCE=1 opt roi_round1      python -m sandesh.roi
echo "ROUND-1 RESULTS READY: results/summary.md, results/explorer.html (heavier add-ons follow)"

# --- add-on: CircuitKIT. Where in the network does the scam take over the action, and
#     does zeroing those attention heads (no training) stop it? Random heads as the control.
opt ck_env   bash scripts/setup_ck.sh
opt ck_pairs python -m sandesh.circuit pairs --model "$BASE"
if [ -x .venv-ck/bin/python ]; then
  opt ck_discover_base .venv-ck/bin/python -m sandesh.circuit discover --model "$BASE" --name base --n "$CK_N"
  if [ -e ckpt/safegrad_sandesh ]; then
    opt ck_discover_safegrad .venv-ck/bin/python -m sandesh.circuit discover --model ckpt/safegrad_sandesh --name safegrad_sandesh --n "$CK_N"
  fi
fi
# CK_SWEEP_N caps the test pairs (the files interleave languages, so any prefix is balanced); dev pairs,
# which choose k, are fewer than that and always used in full.
opt ck_sweep_base python -m sandesh.circuit sweep --model "$BASE" --name base --bs "$BS_MT" ${CK_SWEEP_N:+--limit "$CK_SWEEP_N"}
if [ -e ckpt/safegrad_sandesh ]; then
  opt ck_sweep_safegrad python -m sandesh.circuit sweep --model ckpt/safegrad_sandesh --name safegrad_sandesh --baseline-only \
      --bs "$BS_MT" ${CK_SWEEP_N:+--limit "$CK_SWEEP_N"}
fi
opt ck_knockout      python -m sandesh.circuit knockout --model "$BASE" --out ckpt/base_knockout
opt ck_knockout_rand python -m sandesh.circuit knockout --model "$BASE" --out ckpt/base_knockout_rand --random-seed 0
for name in base_knockout base_knockout_rand; do
  [ -e "ckpt/$name/knockout.json" ] || { echo "[skip] eval $name: no ckpt/$name"; continue; }
  opt "eval_$name" python -m sandesh.evaluate --model "ckpt/$name" --name "$name" --no-harmful --no-benign --bs "$BS_GEN"
  opt "cap_$name"  python -m sandesh.capability --model "ckpt/$name" --name "$name" --n "$MMLU_N" --bs "$BS_MT"
done

# --- add-on: stronger baselines. A spotlighting system prompt, and a guard model filtering the inbox ---
opt eval_base_spotlight python -m sandesh.evaluate --model "$BASE" --name base_spotlight --prompt spotlight --no-harmful --no-benign --bs "$BS_GEN"
attack_addons base_spotlight "$BASE" spotlight
opt guard_detect        python -m sandesh.guard --qwen "$JUDGE" --bs "$BS_GEN"
opt eval_base_guard     python -m sandesh.evaluate --model "$BASE" --name base_guard --inbox-filter data/guard/filter_qwen3guard.jsonl --no-harmful --no-benign --bs "$BS_GEN"

# --- add-on: is SafeGrad better than just mixing the refusals in? ----------------
opt curate_mix     python -m sandesh.curate --only train_mix
opt train_sft_mix  python -m sandesh.train --method plain --data data/curated/train_mix --out ckpt/sft_mix --epochs "$EPOCHS" --bs "$BS_TRAIN"
opt eval_sft_mix   python -m sandesh.evaluate --model ckpt/sft_mix --name sft_mix --bs "$BS_GEN"
weights_addons sft_mix ckpt/sft_mix
attack_addons  sft_mix ckpt/sft_mix base

# --- judge everything new, score, plot ----------------------------------------------
FORCE=1 opt judge    python -m sandesh.safety judge --judge "$JUDGE" --bs "$BS_GEN"
FORCE=1 opt score    python -m sandesh.score
FORCE=1 opt report   python -m sandesh.report
FORCE=1 opt explorer python -m sandesh.explorer
FORCE=1 opt roi      python -m sandesh.roi
echo "ALL DONE. See results/summary.md, results/roi.md, results/explorer.html"
}
main "$@"; exit $?
