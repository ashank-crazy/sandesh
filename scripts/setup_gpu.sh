#!/usr/bin/env bash
# One-time setup on the GPU box. Creates nothing outside $NAS (default /media/NAS/ashank).
#   cd /media/NAS/ashank/sandesh && bash scripts/setup_gpu.sh
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/env.sh
mkdir -p "$HF_HOME" "$UV_CACHE_DIR" "$UV_INSTALL_DIR" "$UV_PYTHON_INSTALL_DIR"

if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$UV_INSTALL_DIR" INSTALLER_NO_MODIFY_PATH=1 sh
fi
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -r requirements.txt
source .venv/bin/activate

python - <<'EOF'
import torch
ok = torch.cuda.is_available()
print("torch", torch.__version__, "cuda:", ok, "|", torch.cuda.get_device_name(0) if ok else "NO GPU")
if not ok:
    raise SystemExit("CUDA not visible. If the driver is older, reinstall torch from the matching index, e.g.\n"
                     "  uv pip install --python .venv/bin/python torch --index-url https://download.pytorch.org/whl/cu121")
EOF
python -m pytest -q tests
echo
echo "Next: hf auth login   (token is stored under $HF_HOME, i.e. inside $NAS)"
echo "      accept the licence at https://huggingface.co/CohereLabs/tiny-aya-fire"
echo "      then: nohup bash scripts/run_all.sh > logs/run_all.log 2>&1 &"
