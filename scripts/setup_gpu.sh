#!/usr/bin/env bash
# One-time setup on the GPU box. Creates nothing outside $NAS (default /media/NAS/ashank).
#   cd /media/NAS/ashank/sandesh && bash scripts/setup_gpu.sh
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/env.sh
mkdir -p "$HF_HOME" "$UV_CACHE_DIR" "$UV_INSTALL_DIR" "$UV_PYTHON_INSTALL_DIR" logs
echo "Setting up in $PWD (caches under $NAS)"

if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$UV_INSTALL_DIR" INSTALLER_NO_MODIFY_PATH=1 sh
fi
# torch on PyPI is built for the newest CUDA (13.x), which a CUDA 12.x driver cannot run. Read the driver's CUDA
# version and, on 12.x, take torch from the CUDA 12.6 index first (the newest torch line with a 12.x build).
drv=$(nvidia-smi 2>/dev/null | grep -o 'CUDA Version: [0-9]*\.[0-9]*' | head -1 | grep -o '[0-9]*\.[0-9]*$' || true)
case "$drv" in
  12.*) TORCH_INDEX=https://download.pytorch.org/whl/cu126 ;;
  *)    TORCH_INDEX= ;;
esac
echo "Driver CUDA version: ${drv:-unknown}; torch from ${TORCH_INDEX:-PyPI}"
# Always rebuild: a venv mixing CUDA 13 and CUDA 12 libraries is not worth debugging.
uv venv .venv --python 3.12 --clear
if [ -n "$TORCH_INDEX" ]; then
  uv pip install --python .venv/bin/python "torch>=2.7" --index-url "$TORCH_INDEX"
fi
uv pip install --python .venv/bin/python -r requirements.txt   # keeps the torch above (it satisfies torch>=2.7)
source .venv/bin/activate

python - <<'EOF'
import torch
ok = torch.cuda.is_available()
print("torch", torch.__version__, "cuda:", ok, "|", torch.cuda.get_device_name(0) if ok else "NO GPU")
if not ok:
    raise SystemExit("CUDA not visible. Check `nvidia-smi` (top right: CUDA Version). If the driver is older than this\n"
                     "torch build needs, reinstall torch from the matching index, then re-run this script, e.g. for 12.6:\n"
                     "  uv pip install --python .venv/bin/python 'torch>=2.7' --index-url https://download.pytorch.org/whl/cu126")
EOF
python -m pytest -q tests
echo
echo "SETUP OK. Next:"
echo "  1. accept the licence at https://huggingface.co/CohereLabs/tiny-aya-fire (any browser, e.g. your phone)"
echo "  2. source scripts/env.sh && hf auth login      (paste a token from https://huggingface.co/settings/tokens;"
echo "     it is stored under $HF_HOME, i.e. inside $NAS)"
echo "  3. nohup bash scripts/run_all.sh > logs/run_all.log 2>&1 &     (see NEXT_STEPS.md for FAST=1 and 3090 knobs)"
