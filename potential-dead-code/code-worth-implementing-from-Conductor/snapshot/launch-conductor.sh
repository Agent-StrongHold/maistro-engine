#!/usr/bin/env bash
set -euo pipefail

# Conductor stack launcher
# Starts: inference engine, gateway, orchestrator

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Cleanup child processes on exit
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

# Health-check helper: poll URL until 200 or timeout
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

echo "=== Starting Conductor Stack ==="
echo ""

# 1. Inference Engine
echo "[1/3] Starting inference engine..."
./start-inference.sh &
PIDS+=($!)
wait_for_health "http://localhost:8080/health" 180 "inference engine"
echo ""

# 2. Gateway
echo "[2/3] Starting gateway..."
python -m uvicorn gateway.server:app --host 0.0.0.0 --port 9090 &
PIDS+=($!)
wait_for_health "http://localhost:9090/health" 15 "gateway"
echo ""

# 3. Orchestrator
echo "[3/3] Starting orchestrator..."
python -m orchestrator.conductor \
  --project example \
  --config projects/example/conductor.yaml &
PIDS+=($!)
echo ""

echo "=== Conductor Stack Running ==="
echo ""
echo "  Inference Engine: PID ${PIDS[0]} (port 8080)"
echo "  Gateway:          PID ${PIDS[1]} (port 9090)"
echo "  Orchestrator:     PID ${PIDS[2]}"
echo ""
echo "Drop task files in your Obsidian vault's conductor/inbox/ folder to begin."
echo "Press Ctrl+C to stop."
echo ""

wait
