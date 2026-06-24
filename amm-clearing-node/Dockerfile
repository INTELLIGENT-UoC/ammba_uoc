FROM python:3.14-slim AS base

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Dependencies layer (cached unless pyproject.toml changes)
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --frozen 2>/dev/null || uv sync --no-dev

# Application layer
COPY configuration.yaml ./
COPY schemas/ ./schemas/
COPY src/ ./src/
# Local off-chain DB simulator (dev-only; only run via the compose "dev" profile)
COPY sim/ ./sim/

EXPOSE 8081

CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8081"]
