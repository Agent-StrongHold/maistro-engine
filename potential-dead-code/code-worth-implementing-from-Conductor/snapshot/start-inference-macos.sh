#!/usr/bin/env bash
set -euo pipefail

# Conductor Inference Engine launcher — macOS (Apple Silicon / Intel)
# For MacBook Air 16GB RAM
# Uses smaller model with reduced context

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LLAMA_CPP_DIR="${LLAMA_CPP_DIR:-$SCRIPT_DIR/../llama.cpp}"
MODEL_PATH="${MODEL_PATH:-$LLAMA_CPP_DIR/models/qwen2.5-coder-7b-instruct-q4_k_m.gguf}"

# KV cache directory
export CONDUCTOR_KV_CACHE_DIR="${CONDUCTOR_KV_CACHE_DIR:-$SCRIPT_DIR/kv-cache}"
mkdir -p "$CONDUCTOR_KV_CACHE_DIR"

echo "Starting inference engine (macOS)..."
echo "  Model: $MODEL_PATH"
echo "  KV cache: $CONDUCTOR_KV_CACHE_DIR"

# Check if model exists
if [ ! -f "$MODEL_PATH" ]; then
  echo ""
  echo "ERROR: Model not found at $MODEL_PATH"
  echo ""
  echo "Download a model first:"
  echo "  # Option 1: Qwen2.5-Coder 7B (recommended, ~4.5GB)"
  echo "  huggingface-cli download Qwen/Qwen2.5-Coder-7B-Instruct-GGUF \\"
  echo "    qwen2.5-coder-7b-instruct-q4_k_m.gguf \\"
  echo "    --local-dir $LLAMA_CPP_DIR/models/"
  echo ""
  echo "  # Option 2: CodeLlama 7B"
  echo "  huggingface-cli download TheBloke/CodeLlama-7B-Instruct-GGUF \\"
  echo "    codellama-7b-instruct.Q4_K_M.gguf \\"
  echo "    --local-dir $LLAMA_CPP_DIR/models/"
  echo ""
  exit 1
fi

# macOS settings for 16GB RAM:
# - 2 slots only (1 template + 1 worker) to fit in memory
# - 8192 context (not 32768) to reduce memory
# - Metal GPU acceleration
"$LLAMA_CPP_DIR/build/bin/llama-server" \
  --model "$MODEL_PATH" \
  --host 0.0.0.0 \
  --port 8080 \
  --n-gpu-layers 99 \
  -np 2 \
  --slot-save-path "$CONDUCTOR_KV_CACHE_DIR" \
  --ctx-size 8192 \
  -b 512 \
  -ub 512 \
  --cache-type-k q8_0 \
  --cache-type-v q8_0 \
  --temp 1.0 \
  --top-p 0.95 \
  --top-k 40
