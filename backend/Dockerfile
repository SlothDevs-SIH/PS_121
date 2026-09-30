# SMRITI backend image — used by the api, worker and migrate services.
# Override PYTHON_IMAGE to build from an internal registry mirror or a base image that
# trusts a corporate TLS-inspection CA (e.g. inside a PSU network).
# Pinned by digest (the multi-arch index; tests/unit/test_image_pins.py checks it). To update:
# docker buildx imagetools inspect python:3.11-slim
ARG PYTHON_IMAGE=python:3.11-slim@sha256:e41613d42d4891e4930f79523f93f81bbc7632584ec65e36ab055f41a800b41e
FROM ${PYTHON_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

# Tesseract OCR (English) for scanned report pages (S1). Only the ingestion worker needs it;
# WITH_OCR=false builds a smaller image (e.g. API-only, or where Debian mirrors are blocked).
ARG WITH_OCR=true
RUN if [ "$WITH_OCR" = "true" ]; then \
        apt-get update \
        && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
        && rm -rf /var/lib/apt/lists/*; \
    fi \
    && pip install --no-cache-dir uv==0.8.17 \
    && useradd --create-home --uid 10001 smriti

WORKDIR /srv/backend

# Dependencies first (cached layer), then the application code.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY alembic.ini ./
COPY app ./app
RUN uv sync --frozen --no-dev

ARG GIT_SHA=unknown
ENV SMRITI_GIT_SHA=$GIT_SHA

USER smriti
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).status == 200 else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
