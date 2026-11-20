#!/usr/bin/env bash
# llama.cpp for P2 (the 4-bit GGUF check), everything under tools/ in the repo folder; nothing system-wide, no sudo,
# no compiler. CPU and network only, so it can run while another job uses the GPU.
#   bash scripts/setup_llama.sh
# 1. The release's prebuilt Ubuntu binaries for CUDA 12.8 (the box's driver) plus its CUDA runtime libraries.
# 2. The same release's source, for convert_hf_to_gguf.py and gguf-py, with the converter's pinned Python
#    requirements in tools/venv-gguf.
# Pinned to one release (LLAMA_TAG to change it); tools/llama_cpp_tag.txt and tools/backend.txt record what is used.
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/env.sh
TAG=${LLAMA_TAG:-b12318}   # 2026-11-12; supports Cohere2 and Tiny Aya's tokenizer ("tiny_aya" pre-tokenizer)
CUDA=${LLAMA_CUDA:-12.8}
T=$PWD/tools
mkdir -p "$T"
REL=https://github.com/ggml-org/llama.cpp/releases/download/$TAG

# --- binaries ----------------------------------------------------------------------------------------
BIN=$T/llama-$TAG-cuda-$CUDA
if [ ! -x "$BIN/llama-server" ]; then
  stage_dir=$T/.unpack-$TAG
  rm -rf "$stage_dir" && mkdir -p "$stage_dir"
  for f in "llama-$TAG-bin-ubuntu-cuda-$CUDA-x64.tar.gz" "cudart-llama-$TAG-bin-ubuntu-cuda-$CUDA-x64.tar.gz"; do
    echo "downloading $f"
    curl -fL --retry 3 -o "$stage_dir/$f" "$REL/$f"
    tar -xzf "$stage_dir/$f" -C "$stage_dir"
    rm -f "$stage_dir/$f"
  done
  server=$(find "$stage_dir" -name llama-server -type f | head -1)
  [ -n "$server" ] || { echo "!!! no llama-server in the release archive"; exit 1; }
  mkdir -p "$BIN"
  mv "$(dirname "$server")"/* "$BIN"/
  # the CUDA runtime archive may unpack elsewhere: put every shared library next to the binaries
  find "$stage_dir" -name "*.so*" \( -type f -o -type l \) -exec mv -n {} "$BIN"/ \;
  rm -rf "$stage_dir"
fi
ln -sfn "$(basename "$BIN")" "$T/bin"
export LD_LIBRARY_PATH="$T/bin${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
"$T/bin/llama-server" --version 2>&1 | tail -2
devices=$("$T/bin/llama-server" --list-devices 2>&1 || true)
echo "$devices"
if echo "$devices" | grep -qi "cuda"; then
  echo cuda > "$T/backend.txt"
else
  echo cpu > "$T/backend.txt"
  echo "[warn] llama.cpp sees no CUDA device: the 4-bit runs would be CPU-only and slow. Send this output to Claude."
fi
echo "$TAG" > "$T/llama_cpp_tag.txt"

# --- converter -------------------------------------------------------------------------------------
if [ ! -f "$T/llama.cpp-$TAG/convert_hf_to_gguf.py" ]; then
  rm -rf "$T/llama.cpp-$TAG"
  git clone --quiet --depth 1 --branch "$TAG" https://github.com/ggml-org/llama.cpp "$T/llama.cpp-$TAG"
fi
ln -sfn "llama.cpp-$TAG" "$T/llama.cpp"
V=$T/venv-gguf
if ! "$V/bin/python" -c "import torch, transformers, sentencepiece" 2>/dev/null; then
  rm -rf "$V"
  uv venv "$V" --python 3.12
  (cd "$T/llama.cpp/requirements" && uv pip install --python "$V/bin/python" -r requirements-convert_hf_to_gguf.txt)
fi
"$V/bin/python" "$T/llama.cpp/convert_hf_to_gguf.py" --help >/dev/null
echo "llama.cpp $TAG ready: $(cat "$T/backend.txt") binaries in tools/bin, converter in tools/llama.cpp (venv tools/venv-gguf)"
