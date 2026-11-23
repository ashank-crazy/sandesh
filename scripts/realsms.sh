#!/usr/bin/env bash
# Final round, P6: real scam SMS written for people (Mishra & Soni, CC BY 4.0; realsms/) in the multi-turn audit.
# 4-bit v2.1 and 4-bit base through llama.cpp, then the P6 verdict fixed in FINAL_ROUND.md. ~30-60 min of GPU.
#   nohup bash scripts/realsms.sh >> logs/realsms.log 2>&1 &
# Knobs (env): BS_GEN (16, = llama-server slots), BF16=1 also runs the bf16 models (adds ~1 h).
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/env.sh
mkdir -p logs

BS_GEN=${BS_GEN:-16}
export SANDESH_LLAMA_PARALLEL=$BS_GEN
echo "[$(date '+%F %T')] realsms $(git rev-parse --short HEAD 2>/dev/null || echo '?'): BS_GEN=$BS_GEN BF16=${BF16:-}"
python -m sandesh.realsms check   # the scenarios committed before the run, unchanged

while pgrep -u "$(id -u)" -f "final_round\.sh|p2\.sh|p3b\.sh|v21\.sh|night\.sh|run_all\.sh|python -m sandesh\.(train|evaluate|multiturn|bon|capability|circuit|safety|guard|gguf)" >/dev/null; do
  echo "[$(date '+%F %T')] another sandesh GPU job is running; waiting"; sleep 120
done

names=()
for m in sft_v21 base; do   # v2.1 first: the model we ship
  f=ckpt/gguf/$m/$m-Q4_K_M.gguf
  [ -f "$f" ] || { echo "missing $f"; exit 1; }
  python -m sandesh.realsms run --model "$f" --name "${m}_q4" --bs "$BS_GEN" 2>&1 | tee "logs/realsms_${m}_q4.log"
  names+=("${m}_q4")
done
if [ -n "${BF16:-}" ]; then
  python -m sandesh.realsms run --model ckpt/sft_v21 --name sft_v21 --bs 16 2>&1 | tee logs/realsms_sft_v21.log
  python -m sandesh.realsms run --model "$SANDESH_BASE" --name base --bs 16 2>&1 | tee logs/realsms_base.log
  names+=(sft_v21 base)
fi
python -m sandesh.realsms score --runs runs --names "${names[@]}"
echo "[$(date '+%F %T')] REALSMS DONE"
