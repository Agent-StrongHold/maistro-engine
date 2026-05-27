# Build from monorepo root:
#   docker build -f packages/hive-conductor/Dockerfile . -t hive-conductor
# Or via docker-compose (context is set to monorepo root in docker-compose.yml).

FROM node:22-alpine AS frontend
WORKDIR /build
COPY packages/hive-conductor/frontend/package.json packages/hive-conductor/frontend/package-lock.json ./
RUN npm ci
COPY packages/hive-conductor/frontend/ ./
ARG VITE_POC_MODE=
ENV VITE_POC_MODE=${VITE_POC_MODE}
# Lets the gateway serve Hive at a sub-path (e.g. VITE_BASE_PATH=/pm/) without
# breaking asset URLs. Defaults to / so standalone builds are unaffected.
ARG VITE_BASE_PATH=/
ENV VITE_BASE_PATH=${VITE_BASE_PATH}
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install maistro-core and maistro-bootstrap from monorepo before requirements.txt
# so hive-conductor can import them without a separate pip install step.
# In dev: pip install -e packages/maistro-core packages/maistro-bootstrap from repo root.
COPY packages/maistro-core /packages/maistro-core
COPY packages/maistro-bootstrap /packages/maistro-bootstrap
RUN pip install --no-cache-dir /packages/maistro-core /packages/maistro-bootstrap

COPY packages/hive-conductor/backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt
COPY packages/hive-conductor/backend/ /app/backend/
COPY packages/hive-conductor/cage/ /app/cage/
COPY packages/hive-conductor/eval/ /app/eval/
COPY packages/hive-conductor/dags/ /app/dags/
COPY --from=frontend /build/dist /app/frontend/dist
ENV PYTHONPATH=/app/backend:/app
EXPOSE 8101
WORKDIR /app/backend
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8101/health/ready || exit 1
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8101"]
