FROM python:3.14-slim AS base

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Dependencies layer (cached unless pyproject.toml changes)
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --frozen 2>/dev/null || uv sync --no-dev

# Application layer
COPY src/ ./src/

# Settlement engine CLI (dry-run planner until the GSY execution environment
# is available; see src/main.py --help).
CMD ["uv", "run", "python", "-m", "src.main"]
