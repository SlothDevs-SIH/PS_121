# SMRITI backend image — used by the api, worker and migrate services.
# Override PYTHON_IMAGE to build from an internal registry mirror or a base image that
# trusts a corporate TLS-inspection CA (e.g. inside a PSU network).
ARG PYTHON_IMAGE=python:3.11-slim
FROM ${PYTHON_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

RUN pip install --no-cache-dir uv==0.8.17 \
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
