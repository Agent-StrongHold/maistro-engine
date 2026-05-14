FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl age \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY packages/maistro-core/ /tmp/maistro-core/
RUN pip install --no-cache-dir /tmp/maistro-core/ && rm -rf /tmp/maistro-core

COPY packages/hive-conductor/backend/requirements.txt /tmp/hc-reqs.txt
RUN pip install --no-cache-dir -r /tmp/hc-reqs.txt && rm -f /tmp/hc-reqs.txt

EXPOSE 8101

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8101"]
