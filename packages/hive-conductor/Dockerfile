# Build from repo root: docker build -f packages/hive-conductor/Dockerfile packages/hive-conductor
# Or from this directory: docker build .

FROM node:22-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt
COPY backend/ /app/backend/
COPY --from=frontend /build/dist /app/frontend/dist
ENV PYTHONPATH=/app/backend
EXPOSE 8101
WORKDIR /app/backend
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8101/health/ready || exit 1
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8101"]
