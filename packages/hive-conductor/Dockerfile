# Build from monorepo root:
#   docker build -f packages/hive-conductor/Dockerfile . -t hive-conductor
# Or via docker-compose (context is set to monorepo root in docker-compose.yml).

# Tip: pin bases by digest and rebuild on a schedule to absorb security patches.
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

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# apt-get upgrade applies Debian security patches; curl removed (the HEALTHCHECK
# now uses stdlib Python); autoremove/clean strip orphaned deps and caches.
RUN apt-get update && apt-get upgrade -y \
    && apt-get autoremove -y --purge \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/* /tmp/*

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

# Drop root: unprivileged system user owning the app tree.
RUN useradd --system --no-create-home --uid 10001 app && chown -R app:app /app
USER 10001

WORKDIR /app/backend
# stdlib healthcheck — no curl in the image.
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8101/health/ready', timeout=4).status==200 else 1)"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8101"]
