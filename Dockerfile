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

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    docker.io \
    curl \
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

EXPOSE 8000

STOPSIGNAL SIGTERM

HEALTHCHECK --interval=10s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/health/live || exit 1

CMD ["uvicorn", "maistro_server.main:app", "--host", "0.0.0.0", "--port", "8000"]
