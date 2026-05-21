#!/usr/bin/env bash
set -euo pipefail

# Conductor Inference Engine launcher
# Hardware: i9-13900K + 128GB RAM + 2x Tesla P40 (48GB VRAM)
# Runs ik_llama.cpp with Qwen3-Coder-Next MoE model

# Paths — adjust these to match your setup
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IK_LLAMA_DIR="${IK_LLAMA_DIR:-$SCRIPT_DIR/../ik_llama.cpp}"
MODEL_PATH="${MODEL_PATH:-$IK_LLAMA_DIR/models/qwen3-coder-next/Qwen3-Coder-Next-UD-Q4_K_XL.gguf}"

# KV cache directory — shared with gateway
export CONDUCTOR_KV_CACHE_DIR="${CONDUCTOR_KV_CACHE_DIR:-$SCRIPT_DIR/kv-cache}"
mkdir -p "$CONDUCTOR_KV_CACHE_DIR"

echo "Starting inference engine..."
echo "  Model: $MODEL_PATH"
echo "  KV cache: $CONDUCTOR_KV_CACHE_DIR"

# GPU/CPU tensor placement: offload all layers, route MoE experts to CPU
# Slot config: 5 slots = 1 template (slot 0) + 4 workers
# Context: 32768 per slot. If OOM, try 16384 and/or reduce to -np 4
# KV cache quantized to q8_0 to reduce VRAM pressure
# --cache-reuse and -sps are ik_llama.cpp-specific; remove if unsupported
"$IK_LLAMA_DIR/build/bin/llama-server" \
  --model "$MODEL_PATH" \
  --host 0.0.0.0 \
  --port 8080 \
  --n-gpu-layers 99 \
  -ot ".ffn_.*_exps.=CPU" \
  -np 5 \
  --slot-save-path "$CONDUCTOR_KV_CACHE_DIR" \
  --ctx-size 32768 \
  -b 4096 \
  -ub 4096 \
  --cache-type-k q8_0 \
  --cache-type-v q8_0 \
  --jinja \
  --temp 1.0 \
  --top-p 0.95 \
  --top-k 40 \
  --min-p 0.01
