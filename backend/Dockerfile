# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.8.4 /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock requirements.txt ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app

ENV PYTHONPATH=/app
ENV PORT=8000
ENV AGENTCORE_RUNTIME_ARN=""
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live')"

CMD ["sh", "-c", "uv run --no-sync uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
