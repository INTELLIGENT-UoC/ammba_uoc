FROM python:3.14-slim AS base

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.8.11 /uv /uvx /bin/

WORKDIR /app

# Dependencies layer (cached unless pyproject.toml or uv.lock change); the
# build fails rather than resolving afresh if uv.lock is missing.
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen

# Application layer
COPY src/ ./src/

# Settlement engine CLI (dry-run planner until the GSY execution environment
# is available; see src/main.py --help).
CMD ["uv", "run", "python", "-m", "src.main"]
