# Source me on the GPU box: keeps every cache, model download and Python install under $NAS.
#   source scripts/env.sh
export NAS=${NAS:-/media/NAS/ashank}
export HF_HOME=$NAS/.cache/huggingface
export XDG_CACHE_HOME=$NAS/.cache
export UV_CACHE_DIR=$NAS/.cache/uv
export UV_PYTHON_INSTALL_DIR=$NAS/.local/python
export UV_INSTALL_DIR=$NAS/.local/bin
export PIP_CACHE_DIR=$NAS/.cache/pip
export TRITON_CACHE_DIR=$NAS/.cache/triton
export TORCHINDUCTOR_CACHE_DIR=$NAS/.cache/inductor
export MPLCONFIGDIR=$NAS/.cache/matplotlib
export WANDB_DISABLED=true WANDB_MODE=disabled
export TOKENIZERS_PARALLELISM=false
# Less fragmentation of GPU memory: helps the borderline cases on a 24 GB card that other jobs share.
[ -n "${PYTORCH_CUDA_ALLOC_CONF:-}" ] || export PYTORCH_ALLOC_CONF=${PYTORCH_ALLOC_CONF:-expandable_segments:True}
export PATH=$UV_INSTALL_DIR:$PATH
export SANDESH_BASE=${SANDESH_BASE:-CohereLabs/tiny-aya-fire}
_here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# `if` (not `[ ] && source`): on a fresh clone there is no .venv yet, and a failing last line would make
# `source scripts/env.sh` return 1, which silently stops any script running under `set -e`.
if [ -f "$_here/.venv/bin/activate" ]; then source "$_here/.venv/bin/activate"; fi
