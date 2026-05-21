FROM python:3.12-slim

WORKDIR /app

COPY packages/maistro-core/src/maistro/ /app/packages/maistro-core/src/maistro/
COPY packages/hive-conductor/backend/ /app/packages/hive-conductor/backend/
COPY packages/hive-conductor/frontend/dist/ /app/packages/hive-conductor/frontend/dist/

RUN pip install --no-cache-dir -r /app/packages/hive-conductor/backend/requirements.txt 2>/dev/null || pip install --no-cache-dir fastapi uvicorn httpx pydantic bcrypt

WORKDIR /app/packages/hive-conductor/backend

EXPOSE 8101

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8101"]
