# Conductor Phase 0: Claude Code Build Instructions

## Goal

Build a local-first autonomous coding orchestration stack ("Conductor") in Phase 0 with these components:

1. Inference Engine (`ik_llama.cpp` + local Qwen3-Coder-Next GGUF)
2. Inference Gateway (Python FastAPI proxy for slots, KV cache, Ultra Think)
3. Conductor Orchestrator (planner/coder/reviewer loop + Obsidian watcher)

All components communicate over HTTP. Build in that order.

Phase 0 is intentionally minimal, but:

- **Conductor is repo-language agnostic**: it can operate on repos written in **Node/TypeScript, C, C++, Python, etc.** as long as the runtime host has the relevant toolchains and you configure project test/build commands.
- **Conductor is component-language agnostic (polyglot)**: when building the Conductor system itself, implement each component in the language that best fits its constraints (performance, safety, iteration speed) as long as it preserves the same interface contracts.

---

## Environment

- Control/UI host: macOS is fine (Cursor/Claude Code authoring, Obsidian vault)
- Runtime host (recommended): Linux x86_64 with NVIDIA driver + CUDA (required for P40 CUDA inference)
- CPU: i9-13900K
- RAM: 128GB
- GPU: 2x NVIDIA Tesla P40 (24GB each)
- Python: 3.11+

> Notes:
> - macOS cannot practically host CUDA on P40; treat the inference box as Linux and access it remotely if your editor is on macOS.
> - P40 is `sm_61` and lacks tensor cores.
> - Some fused MoE CUDA paths may not be available; CPU fallback for expert-heavy paths is acceptable in Phase 0.

### Recommended Toolchains (Runtime Host)

Conductor can edit any language, but to **run builds/tests** you need toolchains installed on the runtime host. If you decide to implement some Conductor components in other languages, you'll also need those build toolchains here.

- Node/TS:
  - `node` (LTS), `npm` (or `pnpm`/`yarn`)
- C/C++:
  - `clang`/`clang++` (or `gcc`/`g++`)
  - `cmake`, `ninja` (recommended), `make`
  - `gdb`/`lldb` (optional), sanitizers (optional)
- Optional (if you implement Gateway/Orchestrator outside Python):
  - Rust: `rustup`, `cargo`
  - Go: `go` toolchain

Example (Ubuntu/Debian):

```bash
sudo apt-get update
sudo apt-get install -y \
  build-essential clang cmake ninja-build pkg-config \
  python3 python3-venv python3-pip \
  nodejs npm
```

---

## Component 1: Inference Engine (`ik_llama.cpp`)

### 1.1 Clone and Build

```bash
git clone https://github.com/ikawrakow/ik_llama.cpp.git
cd ik_llama.cpp

cmake -B build \
  -DBUILD_SHARED_LIBS=OFF \
  -DGGML_CUDA=ON \
  -DCMAKE_CUDA_ARCHITECTURES="61" \
  -DCMAKE_BUILD_TYPE=Release

cmake --build build --config Release -j"$(command -v nproc >/dev/null 2>&1 && nproc || sysctl -n hw.ncpu)" \
  --target llama-server llama-cli llama-bench llama-gguf-split
```

### 1.2 Download Model

```bash
python3 -m pip install huggingface_hub hf_transfer

HF_HUB_ENABLE_HF_TRANSFER=1 huggingface-cli download \
  unsloth/Qwen3-Coder-Next-GGUF \
  --include "*UD-Q4_K_XL*" \
  --local-dir ./models/qwen3-coder-next
```

### 1.3 Discover Available Flags

Before committing flags to the launch script, verify what the built binary supports:

```bash
./build/bin/llama-server --help 2>&1 | grep -iE "cache-reuse|sps|slot-save"
```

If `--cache-reuse` or `-sps` are not listed, remove them from the launch script below. They are ik_llama.cpp-specific and may not exist in all builds.

### 1.4 Launch Script

Create `start-inference.sh`. **All comments are on their own lines above the flags they describe** (bash does not support inline comments inside line continuations):

```bash
#!/usr/bin/env bash
set -euo pipefail

MODEL_PATH="./models/qwen3-coder-next/Qwen3-Coder-Next-UD-Q4_K_XL.gguf"

# KV cache save/restore directory — MUST match gateway config.
# Use an absolute path so both llama-server and the gateway resolve the same location.
KV_CACHE_DIR="${CONDUCTOR_KV_CACHE_DIR:-$(pwd)/kv-cache}"
mkdir -p "$KV_CACHE_DIR"

# GPU/CPU tensor placement: offload all layers, route MoE experts to CPU
# Slot config: 5 slots = 1 template (slot 0) + 4 workers
# Context: 32768 per slot. If OOM, try 16384 and/or reduce to -np 4
# KV cache quantized to q8_0 to reduce VRAM pressure
# --cache-reuse and -sps are ik_llama.cpp-specific; remove if unsupported
./build/bin/llama-server \
  --model "$MODEL_PATH" \
  --host 0.0.0.0 \
  --port 8080 \
  --n-gpu-layers 99 \
  -ot ".ffn_.*_exps.=CPU" \
  -np 5 \
  --slot-save-path "$KV_CACHE_DIR" \
  --ctx-size 32768 \
  -b 4096 \
  -ub 4096 \
  --cache-type-k q8_0 \
  --cache-type-v q8_0 \
  --cache-reuse 256 \
  -sps 0.3 \
  --jinja \
  --temp 1.0 \
  --top-p 0.95 \
  --top-k 40 \
  --min-p 0.01
```

Make executable:

```bash
chmod +x start-inference.sh
```

### 1.5 Validate Engine

```bash
# Step 1: discover the model ID the server assigned
curl -s http://localhost:8080/v1/models | python3 -m json.tool
# Note the "id" field in the response — use it in subsequent requests.

curl -s http://localhost:8080/health

# Step 2: test a completion (replace MODEL_ID with the value from step 1)
curl -s http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"MODEL_ID","messages":[{"role":"user","content":"Write a Python hello world"}],"max_tokens":100}' \
  | python3 -m json.tool
```

Record baseline:
- prompt processing tok/s
- generation tok/s
- first-token latency

---

## Component 2: Inference Gateway

### 2.1 Structure

```text
conductor/
├── gateway/
│   ├── __init__.py
│   ├── server.py
│   ├── slot_manager.py
│   ├── ultra_think.py
│   ├── prefix_cache.py
│   └── config.py
├── tests/
│   ├── conftest.py
│   ├── test_slot_manager.py
│   ├── test_ultra_think.py
│   └── test_prefix_cache.py
├── pyproject.toml
└── README.md
```

### 2.2 API Surface

- `GET  /health` — gateway liveness/readiness (checks self + llama-server)
- `POST /v1/chat/completions` — OpenAI-compatible proxy
- `POST /v1/ultra-think` — parallel diverse generation
- `POST /v1/project/load` — load project context into template slot
- `POST /v1/project/save` — persist template KV cache to disk
- `POST /v1/project/restore` — restore template KV cache from disk
- `GET  /v1/slots/status` — slot utilization, cached prefix lengths
- `GET  /v1/metrics` — throughput, cache hits, timing data

### 2.3 Slot Manager Contract

- Slot `0`: template only (no generation)
- Slots `1-4`: worker generation slots
- Save/restore via llama-server `/slots` API
- Always restore template cache into worker before generation

Track per request:
- `slot_restore_time_ms`
- `prefix_tokens_cached`
- `suffix_tokens_processed`
- `generation_time_ms`
- `tokens_per_second`

### 2.4 Ultra Think Contract

Tier defaults:
- Tier 1: `N=1`
- Tier 2: `N=3` parallel
- Tier 3: `N=5` parallel (with queueing if only 4 workers)
- Tier 4: decompose/escalate

Diversity profile (example):
- candidate1: `temp=0.7, top_p=0.9, top_k=30`
- candidate2: `temp=1.0, top_p=0.95, top_k=40`
- candidate3: `temp=1.2, top_p=0.98, top_k=50`

Use `asyncio.gather()` and pin requests with `id_slot`.

### 2.5 Prefix Cache Manager

Cache layout (rooted at `CONDUCTOR_KV_CACHE_DIR`, shared with llama-server):

```text
$CONDUCTOR_KV_CACHE_DIR/
├── projects/{project_id}/
│   ├── template.bin
│   ├── template.meta.json
│   └── history/
└── metrics/cache_stats.jsonl
```

Invalidation:
- hash of Layer 0 + knowledge context
- hash match: restore from disk
- hash mismatch: recompute template in slot 0 and persist

### 2.6 Gateway Config

```python
from pydantic_settings import BaseSettings

class GatewayConfig(BaseSettings):
    llama_server_url: str = "http://localhost:8080"
    template_slot_id: int = 0
    worker_slot_ids: list[int] = [1, 2, 3, 4]
    kv_cache_dir: str = "./kv-cache"  # override via CONDUCTOR_KV_CACHE_DIR
    tier2_candidates: int = 3
    tier3_candidates: int = 5
    default_max_tokens: int = 4096
    generation_timeout_seconds: int = 300
    slot_restore_timeout_seconds: int = 30
    metrics_log_path: str = "./metrics/gateway.jsonl"

    model_config = {"env_prefix": "CONDUCTOR_"}
```

### 2.7 Required Tests

1. Mock llama-server endpoints (`/v1/chat/completions`, `/slots`, `/health`)
2. Validate slot lifecycle and slot 0 protection
3. Validate Tier 2 concurrent dispatch with correct diversity params
4. Validate cache reuse and invalidation by content hash

---

## Component 3: Conductor Orchestrator

### 3.1 Structure

```text
conductor/
├── orchestrator/
│   ├── __init__.py
│   ├── conductor.py
│   ├── planner.py
│   ├── coder.py
│   ├── reviewer.py
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── layer0.py
│   │   ├── layer1.py
│   │   ├── layer2.py
│   │   ├── changelog.py
│   │   └── knowledge_graph.py
│   ├── interfaces/
│   │   ├── __init__.py
│   │   ├── obsidian_watcher.py
│   │   └── openwebui.py
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── file_ops.py
│   │   ├── shell.py
│   │   ├── git.py
│   │   └── test_runner.py
│   ├── training/
│   │   ├── __init__.py
│   │   ├── data_collector.py
│   │   └── exemplar_library.py
│   └── config.py
└── projects/example/
    ├── conductor.yaml
    └── constraints.md
```

### 3.2 Core Loop (Phase 0)

1. Receive task from Obsidian inbox
2. Load project context via gateway
3. Planner decomposes task
4. For each subtask:
   - estimate tier (heuristic)
   - Ultra Think generate
   - Reviewer score/select
   - apply candidate via sandboxed tool layer
   - run tests
   - retry/escalate as needed
5. Write changelog entry
6. Record training data row
7. Write result back to Obsidian completed file

### 3.3 Language-Agnostic Execution (Phase 0)

Phase 0 should treat language support as a **toolchain + test command selection** problem:

- The LLM can generate code for Node/C/C++/etc.
- The tool layer (`test_runner` + `shell`) runs **project-configured** build/test commands.
- Conductor itself stays generic; each project defines:
  - how to install deps (optional for Phase 0)
  - how to build
  - how to run tests

For Phase 0, keep this intentionally simple:
- Prefer a single `tests.command` string per project (e.g., `npm test` or `ctest --test-dir build`).
- Add smarter auto-detection in Phase 0.5+.

### 3.4 Memory Stack (Phase 0)

Uses numeric naming consistently (Layer 0-4):

- Layer 0: pinned constraints from markdown (always included)
- Layer 1: working memory for active task
- Layer 2: stub (compressed history placeholder)
- Layer 3: JSONL changelog (append-only)
- Layer 4: knowledge graph stub (empty response initially)

### 3.5 Obsidian Interface

Folders:
- `{vault}/conductor/inbox/`
- `{vault}/conductor/completed/`
- `{vault}/conductor/failed/`

Behavior:
- new markdown file in inbox = task
- **debounce**: wait 500ms after last file modification before processing (prevents partial-read race if Obsidian is still writing)
- processing appends result and moves file
- on Layer 0 constraints change, invalidate project prefix cache

### 3.6 Training Data Requirements

Per Ultra Think cycle, record a JSONL row with this schema:

```json
{
  "task_id": "string",
  "timestamp": "ISO8601",
  "prompt_hash": "sha256",
  "tier": 1,
  "candidates": [
    {
      "candidate_id": "string",
      "content_hash": "sha256",
      "sampling_params": {"temp": 0.7, "top_p": 0.9, "top_k": 30},
      "tokens_generated": 1200,
      "generation_time_ms": 15000
    }
  ],
  "reviewer_scores": [
    {
      "candidate_id": "string",
      "scores": {"correctness": 8, "style": 7, "robustness": 6, "simplicity": 9, "testability": 7},
      "overall": 7.4,
      "verdict": "accept"
    }
  ],
  "test_results": [
    {"candidate_id": "string", "passed": true, "summary": "12/12 tests passed"}
  ],
  "accepted_candidate_id": "string or null",
  "human_accepted": null
}
```

Storage: append-only JSONL, one file per project.

---

## Component 4: Integration and Launch

### 4.1 Example Config (`projects/example/conductor.yaml`)

```yaml
project_id: "example"
project_dir: "/path/to/repo"
obsidian_vault: "/path/to/obsidian-vault"
gateway_url: "http://localhost:9090"
inference_url: "http://localhost:8080"
max_retries: 3
accept_threshold: 7.0
max_working_memory_tokens: 8000
layer0_path: "./constraints.md"
training_data_dir: "./training-data"
exemplar_library_dir: "./exemplars"

toolchains:
  node:
    enabled: true
    package_manager: "npm"
  cpp:
    enabled: true
    build_system: "cmake"

tests:
  command: "npm test"
```

### 4.2 Launch Script

Create `launch-conductor.sh` with health-check polling and cleanup trap:

```bash
#!/usr/bin/env bash
set -euo pipefail

# Cleanup child processes on exit
PIDS=()
cleanup() {
  echo "Shutting down..."
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait
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

echo "=== Starting Inference Engine ==="
./start-inference.sh &
PIDS+=($!)
wait_for_health "http://localhost:8080/health" 120 "inference engine"

echo "=== Starting Gateway ==="
uvicorn gateway.server:app --host 0.0.0.0 --port 9090 &
PIDS+=($!)
wait_for_health "http://localhost:9090/health" 15 "gateway"

echo "=== Starting Orchestrator ==="
python -m orchestrator.conductor \
  --project example \
  --config projects/example/conductor.yaml &
PIDS+=($!)

echo ""
echo "Conductor stack running:"
echo "  inference engine: PID ${PIDS[0]} (port 8080)"
echo "  gateway:          PID ${PIDS[1]} (port 9090)"
echo "  orchestrator:     PID ${PIDS[2]}"
echo ""
echo "Drop task files in your Obsidian inbox to begin."

wait
```

---

## Phase 0 Success Criteria

You can proceed to Phase 0.5 only if all are true:

1. Inference engine loads model and responds consistently
2. Prefix caching shows measurable speedup on repeated prefix tasks
3. Tier 2 Ultra Think yields diverse candidate outputs
4. Reviewer scores correlate with manual quality checks on sample tasks
5. Obsidian drop-in -> completed output loop works end-to-end
6. Training JSONL accumulates valid operational traces matching the schema
7. Metrics emitted: tok/s, cache hit rate, latency, acceptance, tier usage

Target baseline:
- first-attempt acceptance rate: >= 30%

---

## Phase 0 Exclusions (Do Not Build Yet)

- Full Layer 4 knowledge graph
- OpenWebUI adapter (stub only)
- Scout daemon
- Fine-tuning pipeline execution (collect data only)
- Multi-project scheduling
- Learned difficulty model (heuristics only)
- Candidate synthesis engine (pick best by reviewer in Phase 0)

---

## Python Dependencies

```toml
[project]
name = "conductor"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.115",
  "uvicorn>=0.34",
  "httpx>=0.28",
  "pydantic>=2.10",
  "pydantic-settings>=2.7",
  "watchdog>=6.0",
  "pyyaml>=6.0",
  "rich>=13.9",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.0",
  "pytest-asyncio>=0.24",
  "pytest-httpx>=0.34",
  "respx>=0.22",
  "ruff>=0.8",
]
```

### Logging

All components use Python `logging` with structured JSON output to stdout. Every log line includes:
- `timestamp` (ISO 8601)
- `level`
- `component` (gateway / orchestrator / watcher)
- `task_id` (when available)
- `trace_id` (propagated across components via `X-Trace-Id` header)

Use `rich` for human-readable console output during development; switch to JSON formatter for production via env var `CONDUCTOR_LOG_FORMAT=json`.

---

## Architecture Invariants

1. **Orchestrator does not directly execute code/commands.** It dispatches to a sandboxed tool layer that performs file writes and shell execution.
2. All model inference calls pass through Gateway.
3. Memory layers are explicit and assembled per request.
4. Slot 0 is template-only.
5. All runs emit structured logs/events.
6. Inference backend is swappable behind OpenAI-compatible Gateway API.
7. Training data is generated from normal operation, not a separate workflow.
8. Conductor is repo-language agnostic; builds/tests are driven by configured toolchains and commands.
9. Conductor is component-language agnostic; contracts (APIs + event/log conventions) are the stable boundary, not the implementation language.
