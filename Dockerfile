FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    docker.io \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy project files
COPY pyproject.toml .
COPY src/ src/
COPY alembic/ alembic/
COPY alembic.ini .

# Install dependencies
RUN uv pip install --system -e ".[dev]"

EXPOSE 8000

CMD ["uvicorn", "maistro.main:app", "--host", "0.0.0.0", "--port", "8000"]
