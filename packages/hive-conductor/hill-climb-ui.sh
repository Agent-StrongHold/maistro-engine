#!/usr/bin/env bash
# Fully automated UI hill-climb loop.
# Runs inside the microVM (or locally with Docker).
#
# Loop: edit → compile → build → restart server → screenshot → score → accept/reject → repeat
#
# Usage: ./hill-climb-ui.sh [component] [passes]
# Example: ./hill-climb-ui.sh Chat.tsx 10

set -euo pipefail

COMPONENT="${1:-Chat.tsx}"
PASSES="${2:-10}"
PORT="${PORT:-8101}"
URL="http://localhost:${PORT}"

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
VENV="$(cd "$ROOT/../.." && pwd)/.venv"
PYTHON="$VENV/bin/python3"
UVICORN="$VENV/bin/uvicorn"

# Source env
set -a; source "$ROOT/../../.env"; set +a
export LITELLM_API_BASE="${LITELLM_PROXY_URL}"
export LITELLM_API_KEY="${LITELLM_PROXY_KEY}"
export PYTHONPATH="$BACKEND:$ROOT/../maistro-core/src:$ROOT"

echo "═══════════════════════════════════════════════"
echo "  UI Hill-Climb: $COMPONENT ($PASSES passes)"
echo "═══════════════════════════════════════════════"

# Start server if not running
if ! curl -s "$URL/health/ready" > /dev/null 2>&1; then
  echo "Starting server..."
  cd "$BACKEND"
  $UVICORN main:app --host 0.0.0.0 --port "$PORT" &>/tmp/hive-hill-climb.log &
  SERVER_PID=$!
  sleep 4
  echo "Server PID: $SERVER_PID"
else
  SERVER_PID=""
  echo "Server already running on $PORT"
fi

# Run the automated loop
cd "$BACKEND"
$PYTHON << PYTHON
import asyncio, httpx, os, subprocess, sys, json, signal, time, base64
from pathlib import Path

FRONTEND = Path("$FRONTEND")
COMPONENT_PATH = FRONTEND / "src/pages/$COMPONENT"
URL = "$URL"
PORT = "$PORT"
PASSES = $PASSES
BASE = os.environ["LITELLM_API_BASE"].rstrip("/")
if not BASE.endswith("/v1"): BASE += "/v1"
KEY = os.environ["LITELLM_API_KEY"]
PYTHON_BIN = "$PYTHON"
UVICORN_BIN = "$UVICORN"

def restart_server():
    """Kill and restart uvicorn to serve new frontend build."""
    subprocess.run(["pkill", "-f", f"uvicorn.*--port {PORT}"], capture_output=True)
    time.sleep(1)
    subprocess.Popen(
        [UVICORN_BIN, "main:app", "--host", "0.0.0.0", "--port", PORT],
        cwd=str(Path("$BACKEND")),
        stdout=open("/tmp/hive-hill-climb.log", "a"),
        stderr=subprocess.STDOUT,
        env={**os.environ},
    )
    time.sleep(3)

def build_frontend():
    """Compile + build frontend."""
    r = subprocess.run(["npx", "tsc", "--noEmit"], cwd=str(FRONTEND), capture_output=True, text=True)
    if r.returncode != 0:
        return False, r.stdout[:200]
    subprocess.run(["npm", "run", "build"], cwd=str(FRONTEND), capture_output=True)
    return True, ""

async def screenshot():
    """Screenshot via playwright."""
    script = '''
import asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 800})
        await page.goto("''' + URL + '''/", wait_until="networkidle", timeout=10000)
        # Login
        try:
            await page.fill('input[type="text"]', "test", timeout=3000)
            await page.fill('input[type="password"]', "user1234")
            await page.click('button[type="submit"]')
            await page.wait_for_timeout(2000)
        except: pass
        await page.goto("''' + URL + '''/chat", wait_until="networkidle", timeout=10000)
        await page.wait_for_timeout(1000)
        buf = await page.screenshot(type="png")
        await browser.close()
        import base64; print(base64.b64encode(buf).decode())
asyncio.run(main())
'''
    r = subprocess.run([PYTHON_BIN, "-c", script], capture_output=True, text=True, timeout=30)
    return r.stdout.strip() if r.returncode == 0 else None

async def score(img_b64):
    """Score with vision model."""
    if not img_b64:
        return {"score": 0, "top_issue": "screenshot failed", "fix": "fix playwright"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(f"{BASE}/chat/completions",
            headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
            json={"model": "gemini-3.5-flash", "messages": [{"role": "user", "content": [
                {"type": "text", "text": "Score this AI chat UI 0-100 vs ChatGPT/Linear. JSON: {\"score\": int, \"top_issue\": str, \"fix\": str}"},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
            ]}], "response_format": {"type": "json_object"}})
        r.raise_for_status()
        return json.loads(r.json()["choices"][0]["message"]["content"])

async def generate_edit(code, feedback):
    """Generate one targeted edit."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(f"{BASE}/chat/completions",
            headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
            json={"model": "gemini-3.5-flash", "messages": [{"role": "user", "content": f"""ONE targeted fix. ISSUE: {feedback}
CODE:
```
{code[:5000]}
```
JSON: {{"description": "fix", "old": "exact substring", "new": "replacement"}}"""}],
                "response_format": {"type": "json_object"}})
        r.raise_for_status()
        return json.loads(r.json()["choices"][0]["message"]["content"])

async def main():
    best_score = 0
    for i in range(PASSES):
        print(f"\n{'='*50}")
        print(f"  PASS {i+1}/{PASSES}")
        print(f"{'='*50}")

        # Screenshot + score
        img = await screenshot()
        if img:
            result = await score(img)
            s = result.get("score", 0)
            issue = result.get("top_issue", "unknown")
            fix = result.get("fix", "")
            Path(f"/tmp/hive-ui-pass-{i+1}.png").write_bytes(base64.b64decode(img))
            print(f"  Score: {s}/100 (best: {best_score})")
            print(f"  Issue: {issue[:80]}")
            print(f"  Fix: {fix[:80]}")
            if s > best_score:
                best_score = s
        else:
            print("  ⚠ Screenshot failed — using code-only feedback")
            issue = "improve accessibility and responsive design"
            fix = issue

        # Generate edit
        code = COMPONENT_PATH.read_text()
        edit = await generate_edit(code, f"{issue}. {fix}")
        if not edit or not edit.get("old") or edit["old"] not in code:
            print(f"  ✗ Edit not applicable: {edit.get('description', '?') if edit else 'none'}")
            continue

        # Apply
        backup = code
        COMPONENT_PATH.write_text(code.replace(edit["old"], edit["new"], 1))

        # Compile + build
        ok, err = build_frontend()
        if not ok:
            COMPONENT_PATH.write_text(backup)
            print(f"  ✗ Compile failed — reverted")
            continue

        # Restart server
        restart_server()
        print(f"  ✓ {edit.get('description', 'applied')}")
        print(f"    Server restarted. Screenshot next pass.")

    print(f"\n{'='*50}")
    print(f"  DONE — best score: {best_score}/100")
    print(f"{'='*50}")

asyncio.run(main())
PYTHON

# Cleanup
if [ -n "$SERVER_PID" ]; then
  echo "Stopping server (PID $SERVER_PID)"
  kill "$SERVER_PID" 2>/dev/null || true
fi
