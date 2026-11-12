#!/usr/bin/env bash
# CircuitKIT environment (.venv-ck), next to the main .venv. CircuitKIT 0.2.3 pins
# huggingface-hub<2 and transformer-lens 3.8, so it gets its own venv; torch is the same
# build as the main venv's (same CUDA). Creates nothing outside the repo folder.
#   bash scripts/setup_ck.sh
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/env.sh
if [ -x .venv-ck/bin/python ] && .venv-ck/bin/python -c "import circuitkit" 2>/dev/null; then
  echo "CircuitKIT env ready (.venv-ck)"; exit 0
fi
TV=$(.venv/bin/python -c "import torch; print(torch.__version__)")
rm -rf .venv-ck
uv venv .venv-ck --python 3.12
case "$TV" in
  *+cu*) uv pip install --python .venv-ck/bin/python "torch==${TV%%+*}" --extra-index-url "https://download.pytorch.org/whl/${TV##*+}" ;;
  *)     uv pip install --python .venv-ck/bin/python "torch==$TV" ;;
esac
uv pip install --python .venv-ck/bin/python -r requirements-ck.txt
.venv-ck/bin/python - <<'PY'
import torch, circuitkit
print("circuitkit", circuitkit.__version__, "| torch", torch.__version__, "| cuda", torch.cuda.is_available())
if not torch.cuda.is_available():
    raise SystemExit("CUDA not visible in .venv-ck; CircuitKIT discovery on a 3B model needs the GPU")
PY
