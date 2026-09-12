FROM python:3.11-slim

WORKDIR /app

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency spec first for layer caching
COPY pyproject.toml ./
RUN uv pip install --system --no-cache ".[dev]"

# Include migrations so a fresh container can initialize its database before serving.
COPY alembic.ini ./
COPY alembic/ ./alembic/

# Copy backend source
COPY src/ ./src/

# The optimizer package is mounted as a volume by docker-compose.yml
# (./optimizer:/app/optimizer), so it is NOT copied here.

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn src.main:app --host 0.0.0.0 --port 8000"]
