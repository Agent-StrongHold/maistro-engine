# ═══════════════════════════════════════════════════════════════════════════════
# Fantasia Engine — Multi-stage Wolfi build
# Stage 1: Build frontend (Node)
# Stage 2: Runtime (Python on Wolfi — minimal, secure, no bloat)
# ═══════════════════════════════════════════════════════════════════════════════

# ── Stage 1: Frontend build ──────────────────────────────────────────────────
FROM node:20-alpine AS frontend-build
WORKDIR /build
COPY packages/hive-conductor/frontend/package.json packages/hive-conductor/frontend/package-lock.json ./
RUN npm ci --ignore-scripts
COPY packages/hive-conductor/frontend/ ./
RUN npm run build

# ── Stage 2: Runtime ─────────────────────────────────────────────────────────
FROM cgr.dev/chainguard/python:latest-dev AS runtime

WORKDIR /app

# System deps (Wolfi uses apk)
USER root
RUN apk add --no-cache git bash curl

# Python deps
COPY packages/hive-conductor/backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Backend code
COPY packages/hive-conductor/backend/ /app/backend/

# Frontend static build from stage 1
COPY --from=frontend-build /build/dist /app/frontend/dist

# Data files (widget configs, DAG templates, demos)
COPY packages/hive-conductor/backend/data/ /app/backend/data/

# Startup script
COPY packages/hive-conductor/backend/start.sh /app/start.sh
RUN chmod +x /app/start.sh

# Non-root user
RUN adduser -D -u 1000 hive
USER hive

# Env defaults (overridden by docker-compose / Launch / vault)
ENV LITELLM_API_BASE="" \
    LITELLM_API_KEY="" \
    CHAT_DEFAULT_MODEL="claude-sonnet-4-6" \
    JIRA_PAT="" \
    AIRTABLE_TOKEN="" \
    AIRTABLE_BASE_ID="" \
    PORT=8101

EXPOSE 8101

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8101/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8101", "--app-dir", "/app/backend"]
