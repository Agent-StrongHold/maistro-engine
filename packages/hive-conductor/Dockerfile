# Build from monorepo root:
#   docker build -f packages/hive-conductor/Dockerfile . -t hive-conductor
# Or via docker-compose (context is set to monorepo root in docker-compose.yml).
#
# Runtime is a Chainguard/Wolfi base (glibc, nonroot uid 65532, no shell/pip,
# near-zero CVEs) so the image scan finds no fixable HIGH/CRITICAL CVEs — the
# CVE-laden debian-slim base was the sole source of the container-scan failures.
# Pattern mirrors Dockerfile.chainguard: fat -dev builder makes a self-contained
# venv; thin runtime copies only the venv + app sources.

# ---- frontend build ----
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

# ---- fat Wolfi builder: self-contained venv (has shell/pip/apk, glibc) ----
FROM cgr.dev/chainguard/python:latest-dev AS pybuild
WORKDIR /app
ENV PATH="/app/venv/bin:$PATH"
# age powers the SPEC-011 secrets vault (maistro/vault.py shells out to it);
# first-run setup provisions the vault, so the runtime image must carry the
# static binaries (SPEC-072726-3439 Phase 3). The free Chainguard APK repo is
# authenticated (apk add age fails without HTTP_AUTH), so fetch the official
# static release with a pinned checksum instead.
ARG TARGETARCH
ARG AGE_VERSION=1.3.1
ARG AGE_SHA256_AMD64=bdc69c09cbdd6cf8b1f333d372a1f58247b3a33146406333e30c0f26e8f51377
ARG AGE_SHA256_ARM64=c6878a324421b69e3e20b00ba17c04bc5c6dab0030cfe55bf8f68fa8d9e9093a
USER root
RUN set -e; \
    arch="${TARGETARCH:-amd64}"; \
    if [ "$arch" = "arm64" ]; then sha="$AGE_SHA256_ARM64"; else sha="$AGE_SHA256_AMD64"; fi; \
    wget -qO /tmp/age.tgz "https://github.com/FiloSottile/age/releases/download/v${AGE_VERSION}/age-v${AGE_VERSION}-linux-${arch}.tar.gz"; \
    echo "$sha  /tmp/age.tgz" | sha256sum -c -; \
    tar -xzf /tmp/age.tgz -C /tmp; \
    install -m 0755 /tmp/age/age /tmp/age/age-keygen /usr/local/bin/; \
    rm -rf /tmp/age /tmp/age.tgz
USER 65532
RUN python -m venv /app/venv
# Install the maistro library packages (non-editable) so the venv is fully
# self-contained — nothing from these source trees is needed at runtime.
# maistro-design/-evolve back the conductor's design + evolution routes;
# routes/design.py imports maistro_design at module load (unguarded), so the
# app will not boot without it. maistro-canvas is a hard dep of maistro-design.
COPY packages/maistro-core /packages/maistro-core
COPY packages/maistro-bootstrap /packages/maistro-bootstrap
COPY packages/maistro-canvas /packages/maistro-canvas
COPY packages/maistro-design /packages/maistro-design
COPY packages/maistro-evolve /packages/maistro-evolve
# NOTE: maistro-core's [identity] extra (bip-utils → coincurve) cannot install
# here yet: coincurve publishes no cp314 wheels (21.0.0 caps at cp313), this
# base image is Python 3.14, and coincurve's source build is broken against
# current cffi. Until a cp314 wheel exists, setup surfaces the gap loudly via
# identity_unavailable instead of a silently-missing mnemonic
# (SPEC-072726-3439 Phase 3 tracks restoring in-image identity).
RUN pip install --no-cache-dir \
    /packages/maistro-core \
    /packages/maistro-bootstrap \
    /packages/maistro-canvas \
    /packages/maistro-design \
    /packages/maistro-evolve
COPY packages/hive-conductor/backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt && \
    pip install --no-cache-dir "setuptools>=78.1.1"
# Seed dir for conductor state (SQLite/vault/state). Created under the writable
# /app workdir because the -dev base runs as nonroot and cannot write to /. The
# runtime stage COPY --chown's it to /data so a mounted named volume inherits
# writable nonroot ownership.
RUN mkdir -p /app/state_seed

# ---- thin Wolfi runtime: near-0-CVE base, nonroot, no shell/pip ----
FROM cgr.dev/chainguard/python:latest
WORKDIR /app
ENV PATH="/app/venv/bin:$PATH" \
    PYTHONPATH=/app/backend:/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
COPY --from=pybuild /app/venv /app/venv
COPY --from=pybuild /usr/local/bin/age /usr/local/bin/age-keygen /usr/bin/
COPY packages/hive-conductor/backend/ /app/backend/
COPY packages/hive-conductor/cage/ /app/cage/
COPY packages/hive-conductor/eval/ /app/eval/
COPY packages/hive-conductor/dags/ /app/dags/
COPY --from=frontend /build/dist /app/frontend/dist
# Persistent conductor state dir, pre-owned by the nonroot uid (see pybuild).
COPY --from=pybuild --chown=65532:65532 /app/state_seed /data
EXPOSE 8101
WORKDIR /app/backend
# Chainguard runs as nonroot (uid 65532) by default; make it explicit so the
# image is unambiguously non-root.
USER 65532
# exec-form, stdlib healthcheck — no curl/shell in the image.
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8101/health/ready', timeout=4).status==200 else 1)"]
# Base image's ENTRYPOINT is `python`, so invoke uvicorn via `python -m`.
ENTRYPOINT ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8101"]
