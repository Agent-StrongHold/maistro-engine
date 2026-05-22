# ─── Build stage ───────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock README.md ./
COPY packages/maistro-core packages/maistro-core
COPY packages/maistro-server packages/maistro-server

# Production API: editable core (with extras used by the server) + server
RUN uv pip install --system \
    -e "./packages/maistro-core[llm,sandbox,observability]" \
    -e "./packages/maistro-server"


# ─── Production stage ─────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies + headless Chromium runtime deps for
# browser-use (Day 4 — RESEARCH agent's web tool). The Chromium binary
# itself comes from `playwright install chromium` below.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    docker.io \
    curl \
    wget \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libpango-1.0-0 libcairo2 libasound2 libatspi2.0-0 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Application sources (editable installs reference these paths)
COPY packages/maistro-core packages/maistro-core
COPY packages/maistro-server packages/maistro-server
COPY alembic/ alembic/
COPY alembic.ini .
COPY pyproject.toml uv.lock README.md ./

# Re-resolve editable installs against copied trees
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
RUN uv pip install --system \
    -e "./packages/maistro-core[llm,sandbox,observability]" \
    -e "./packages/maistro-server" \
    "alembic>=1.14"

# Install browser-use + Playwright + Chromium for the RESEARCH role's
# web tool (Day 4). Pinned versions chosen for stability; v1 may relax
# to a range. browser-use uses Playwright under the hood; we install
# Chromium binary explicitly (apt deps already in the system layer
# above). gemini-3.1-flash-lite drives browser actions via the JedAI
# gateway (configured at runtime in maistro.tools.browser.client).
RUN uv pip install --system \
    "browser-use>=0.1.40" \
    "playwright>=1.49.0" \
 && python -m playwright install chromium

EXPOSE 8000

STOPSIGNAL SIGTERM

HEALTHCHECK --interval=10s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/health/live || exit 1

CMD ["uvicorn", "maistro_server.main:app", "--host", "0.0.0.0", "--port", "8000"]
