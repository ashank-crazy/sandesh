#!/usr/bin/env bash
# Final round, P2: the models as 4-bit GGUF files run by llama.cpp (what a phone app would ship). Resumable like
# final_round.sh: each finished stage drops a marker in .done/ (names start with g_) and is skipped on a re-run.
#   nohup bash scripts/p2.sh >> logs/p2.log 2>&1 &
#
# Part 1, CPU and network only (safe next to a GPU job): llama.cpp into tools/, then base, PlainSFT and v2 converted
# to GGUF and quantized to Q4_K_M, plus Cohere's own Q4_K_M of the base as a check on our conversion.
# Part 2, GPU: waits until no other sandesh GPU job runs, then for each 4-bit file: the four test splits with the
# harmful and XSTest prompts, the multi-turn audit, best-of-N, and speed (GPU, and CPU alone). Then judge and score.
#
# Knobs (env): BS_GEN (16, = llama-server slots), MT_PER_LANG (20), JUDGE (Qwen/Qwen3Guard-Gen-4B).
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/env.sh
mkdir -p logs .done

BS_GEN=${BS_GEN:-16}
MT_PER_LANG=${MT_PER_LANG:-20}
JUDGE=${JUDGE:-Qwen/Qwen3Guard-Gen-4B}
export SANDESH_LLAMA_PARALLEL=$BS_GEN

stage() {  # stage <name> <command...>
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

main() {
[ $# -gt 0 ] && ONLY="$*"
echo "[$(date '+%F %T')] p2 $(git rev-parse --short HEAD 2>/dev/null || echo '?'): BS_GEN=$BS_GEN MT=$MT_PER_LANG ${ONLY:+ONLY=$ONLY}"

# --- part 1: CPU / network ---------------------------------------------------------------------------
stage g_setup bash scripts/setup_llama.sh
opt g_convert_base python -m sandesh.gguf convert --model "$SANDESH_BASE" --name base
opt g_convert_sft  python -m sandesh.gguf convert --model ckpt/sft_sandesh --name sft_sandesh
opt g_convert_v2   python -m sandesh.gguf convert --model ckpt/sft_v2 --name sft_v2
opt g_fetch_cohere python -m sandesh.gguf fetch --name base_cohere
FORCE=1 opt g_compare python -m sandesh.gguf compare --name base_cohere --names base sft_sandesh sft_v2

# --- part 2: GPU ----------------------------------------------------------------------------------------
while pgrep -u "$(id -u)" -f "final_round\.sh|run_all\.sh|python -m sandesh\.(train|evaluate|multiturn|bon|capability|circuit|safety|guard)" >/dev/null; do
  echo "[$(date '+%F %T')] another sandesh GPU job is running; waiting"; sleep 120
done
for m in sft_v2 base sft_sandesh base_cohere; do   # v2 first: the model we ship
  f=ckpt/gguf/$m/$m-Q4_K_M.gguf
  [ -f "$f" ] || { echo "[skip] $m: no $f"; continue; }
  n=${m}_q4
  opt "g_eval_$n"  python -m sandesh.evaluate --model "$f" --name "$n" --bs "$BS_GEN"
  opt "g_mt_$n"    python -m sandesh.multiturn --model "$f" --name "$n" --per-lang "$MT_PER_LANG" --bs "$BS_GEN"
  opt "g_bon_$n"   python -m sandesh.bon run --model "$f" --name "$n" --bs "$BS_GEN"
  opt "g_bench_$n" python -m sandesh.gguf bench --gguf "$f" --name "$n"
done
FORCE=1 opt g_judge  python -m sandesh.safety judge --judge "$JUDGE" --bs 32
FORCE=1 opt g_score  python -m sandesh.score
FORCE=1 opt g_report python -m sandesh.report
echo "[$(date '+%F %T')] P2 DONE: results/summary.md (section: on the phone, 4-bit)"
}
main "$@"; exit
