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
$PY -m sandesh.safety benign --data "$W/data" --smoke
echo "== 3. safety anchor"; $PY -m sandesh.safety anchor --data "$W/data" --model "$M" --judge "$J" --bs 8
echo "== 4. curate";  $PY -m sandesh.curate --data "$W/data" --only train train_clean dev safety train_mix
echo "== 5. train";
$PY -m sandesh.train --method plain --data "$W/data/curated/train_clean" --out "$W/ckpt/sft_clean" --epochs 0.1 --bs 2 --device cpu --no-grad-ckpt
$PY -m sandesh.train --method safegrad --data "$W/data/curated/train" --safety "$W/data/curated/safety" --out "$W/ckpt/safegrad_sandesh" --epochs 0.1 --bs 2 --device cpu --no-grad-ckpt
$PY -m sandesh.train --method plain --data "$W/data/curated/train_mix" --out "$W/ckpt/sft_mix" --epochs 0.05 --bs 2 --device cpu --no-grad-ckpt
EV="--data $W/data --runs $W/runs --limit 12 --bs 6 --max-new-tokens 64"
echo "== 6. evaluate"
$PY -m sandesh.evaluate --model "$M" --name base $EV
$PY -m sandesh.evaluate --model "$M" --name base_defensive --prompt defensive --no-harmful --no-benign $EV
$PY -m sandesh.evaluate --model "$M" --name base_spotlight --prompt spotlight --no-harmful --no-benign $EV
$PY -m sandesh.evaluate --model "$W/ckpt/safegrad_sandesh" --name safegrad_sandesh $EV
$PY -m sandesh.evaluate --model "$W/ckpt/sft_mix" --name sft_mix $EV
$PY -m sandesh.evaluate --model "$M" --name base --splits $EV   # no-op: everything exists
echo "== 7. detectors"
$PY -m sandesh.guard --data "$W/data" --qwen "$J" --limit 3 --bs 8
$PY -m sandesh.evaluate --model "$M" --name base_guard --inbox-filter "$W/data/guard/filter_qwen3guard.jsonl" --no-harmful --no-benign $EV
echo "== 8. best-of-N"
$PY -m sandesh.bon build --data "$W/data" --per-lang 1 --k 3
for c in "base|$M|base" "base_spotlight|$M|spotlight" "safegrad_sandesh|$W/ckpt/safegrad_sandesh|base"; do
  IFS='|' read -r n m pr <<< "$c"
  $PY -m sandesh.bon run --data "$W/data" --runs "$W/runs" --model "$m" --name "$n" --prompt "$pr" --bs 6 --max-new-tokens 64
done
echo "== 9. multi-turn"
for c in "base|$M|base" "safegrad_sandesh|$W/ckpt/safegrad_sandesh|base"; do
  IFS='|' read -r n m pr <<< "$c"
  $PY -m sandesh.multiturn --data "$W/data" --runs "$W/runs" --model "$m" --name "$n" --prompt "$pr" --per-lang 1 --bs 6 --max-new-tokens 48
done
echo "== 10. capability"
$PY -m sandesh.capability --runs "$W/runs" --model "$M" --name base --n 3 --bs 6
$PY -m sandesh.capability --runs "$W/runs" --model "$W/ckpt/safegrad_sandesh" --name safegrad_sandesh --n 3 --bs 6
echo "== 10b. CircuitKIT"
PY_CK=${PY_CK:-.venv-ck/bin/python}
$PY -m sandesh.circuit pairs --data "$W/data" --model "$M"
if [ -x "$PY_CK" ]; then
  CK="--data $W/data --runs $W/runs"
  $PY_CK -m sandesh.circuit discover $CK --model "$M" --name base --n 2 --ig-steps 2 --dtype float32 --cpu-ok
  $PY_CK -m sandesh.circuit discover $CK --model "$W/ckpt/safegrad_sandesh" --name safegrad_sandesh --n 2 --ig-steps 2 --dtype float32 --cpu-ok
  $PY -m sandesh.circuit sweep $CK --model "$M" --name base --limit 4 --n-random 1
  $PY -m sandesh.circuit sweep $CK --model "$W/ckpt/safegrad_sandesh" --name safegrad_sandesh --baseline-only --limit 4
  $PY -m sandesh.circuit knockout $CK --model "$M" --out "$W/ckpt/base_knockout" --k 2
  $PY -m sandesh.circuit knockout $CK --model "$M" --out "$W/ckpt/base_knockout_rand" --k 2 --random-seed 0
  $PY -m sandesh.evaluate --model "$W/ckpt/base_knockout" --name base_knockout --no-harmful --no-benign $EV
  $PY -m sandesh.evaluate --model "$W/ckpt/base_knockout_rand" --name base_knockout_rand --no-harmful --no-benign $EV
  $PY -m sandesh.capability --runs "$W/runs" --model "$W/ckpt/base_knockout" --name base_knockout --n 3 --bs 6
else
  echo "(no CircuitKIT env at $PY_CK: skipping attribution and knockout)"
fi
echo "== 11. judge";  $PY -m sandesh.safety judge --data "$W/data" --runs "$W/runs" --judge "$J" --bs 8
echo "== 12. score";  $PY -m sandesh.score --data "$W/data" --runs "$W/runs" --out "$W/results"
echo "== 13. report"; $PY -m sandesh.report --results "$W/results"
$PY -m sandesh.explorer --data "$W/data" --runs "$W/runs" --results "$W/results" --out "$W/results/explorer.html"
$PY -m sandesh.roi --runs "$W/runs" --out "$W/results"
echo "SMOKE OK -> $W"
