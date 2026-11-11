#!/usr/bin/env bash
# End-to-end pipeline check on a tiny model, CPU only. Proves every stage runs;
# the numbers mean nothing. Usage: bash scripts/smoke_local.sh [workdir]
set -euo pipefail
cd "$(dirname "$0")/.."
W=${1:-${TMPDIR:-/tmp}/sandesh_smoke}
M=${SMOKE_MODEL:-HuggingFaceTB/SmolLM2-135M-Instruct}
J=${SMOKE_JUDGE:-Qwen/Qwen3Guard-Gen-0.6B}
export SANDESH_BASE=$M TQDM_MININTERVAL=30 TOKENIZERS_PARALLELISM=false
rm -rf "$W" && mkdir -p "$W"
PY=${PY:-python}

echo "== 1. world";   $PY -m sandesh.world --out "$W/data" --smoke
echo "== 2. safety prompts"; $PY -m sandesh.safety build --data "$W/data" --smoke
echo "== 3. safety anchor"; $PY -m sandesh.safety anchor --data "$W/data" --model "$M" --judge "$J" --bs 8
echo "== 4. curate";  $PY -m sandesh.curate --data "$W/data"
echo "== 5. train";
$PY -m sandesh.train --method plain --data "$W/data/curated/train_clean" --out "$W/ckpt/sft_clean" --epochs 0.1 --bs 2 --device cpu --no-grad-ckpt
$PY -m sandesh.train --method safegrad --data "$W/data/curated/train" --safety "$W/data/curated/safety" --out "$W/ckpt/safegrad_sandesh" --epochs 0.1 --bs 2 --device cpu --no-grad-ckpt
echo "== 6. evaluate"
$PY -m sandesh.evaluate --model "$M" --name base --data "$W/data" --runs "$W/runs" --limit 12 --bs 6 --max-new-tokens 64
$PY -m sandesh.evaluate --model "$M" --name base_defensive --prompt defensive --data "$W/data" --runs "$W/runs" --limit 12 --bs 6 --max-new-tokens 64
$PY -m sandesh.evaluate --model "$W/ckpt/safegrad_sandesh" --name safegrad_sandesh --data "$W/data" --runs "$W/runs" --limit 12 --bs 6 --max-new-tokens 64
echo "== 7. judge";  $PY -m sandesh.safety judge --data "$W/data" --runs "$W/runs" --judge "$J" --bs 8
echo "== 8. score";  $PY -m sandesh.score --data "$W/data" --runs "$W/runs" --out "$W/results"
echo "SMOKE OK -> $W"
