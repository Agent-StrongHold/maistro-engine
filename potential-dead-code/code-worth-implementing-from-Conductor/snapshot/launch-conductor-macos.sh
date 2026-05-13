#!/usr/bin/env bash
set -euo pipefail

# Conductor stack launcher — macOS version
# For MacBook Air 16GB

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Export macOS-optimized gateway settings
export CONDUCTOR_WORKER_SLOT_IDS="[1]"
export CONDUCTOR_TIER1_CANDIDATES=1
export CONDUCTOR_TIER2_CANDIDATES=1
export CONDUCTOR_TIER3_CANDIDATES=2
export CONDUCTOR_DEFAULT_MAX_TOKENS=2048

# Cleanup on exit
PIDS=()
cleanup() {
  echo ""
  echo "Shutting down Conductor stack..."
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
  echo "Shutdown complete."
}
trap cleanup EXIT INT TERM

# Health check
wait_for_health() {
  local url="$1" timeout="$2" label="$3"
  local elapsed=0
  echo "Waiting for $label at $url ..."
  while ! curl -sf "$url" > /dev/null 2>&1; do
    sleep 1
    elapsed=$((elapsed + 1))
    if [ "$elapsed" -ge "$timeout" ]; then
      echo "ERROR: $label did not become healthy within ${timeout}s"
      exit 1
    fi
  done
  echo "$label is healthy (${elapsed}s)"
}

echo "=== Starting Conductor Stack (macOS) ==="
echo ""

# 1. Inference Engine
echo "[1/3] Starting inference engine..."
./start-inference-macos.sh &
PIDS+=($!)
wait_for_health "http://localhost:8080/health" 120 "inference engine"
echo ""

# 2. Gateway
echo "[2/3] Starting gateway..."
source .venv/bin/activate
python -m uvicorn gateway.server:app --host 127.0.0.1 --port 9090 &
PIDS+=($!)
wait_for_health "http://localhost:9090/health" 15 "gateway"
echo ""

# 3. Orchestrator
echo "[3/3] Starting orchestrator..."
python -m orchestrator.conductor \
  --project macos-example \
  --config projects/macos-example/conductor.yaml &
PIDS+=($!)
echo ""

echo "=== Conductor Stack Running (macOS) ==="
echo ""
echo "  Inference Engine: PID ${PIDS[0]} (port 8080)"
echo "  Gateway:          PID ${PIDS[1]} (port 9090)"
echo "  Orchestrator:     PID ${PIDS[2]}"
echo ""
echo "To test manually:"
echo "  curl http://localhost:9090/health"
echo ""
echo "Press Ctrl+C to stop."
echo ""

wait
