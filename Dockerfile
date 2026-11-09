FROM python:3.12.8-slim-bookworm@sha256:2199a62885a12290dc9c5be3ca0681d367576ab7bf037da120e564723292a2f0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr=5.3.0-2 \
        tesseract-ocr-por=1:4.1.0-2 \
        libtesseract5=5.3.0-2 \
    && tesseract --version | grep -Eq '^tesseract 5\.' \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY alembic.ini ./
COPY migrations ./migrations
COPY scripts ./scripts
RUN python -m pip install --no-cache-dir uv==0.12.8 \
    && uv sync --locked --no-dev

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data/uploads /app/data/processed \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "doc_audit.main:app", "--host", "0.0.0.0", "--port", "8000"]
