# One Dockerfile, three images: web, insights, ingest.
#
# Build from the demo/ directory, for example:
#   docker build -f docker/Dockerfile --target web -t football-insights-web:local .
#
# The build context is demo/, which never contains data: the datasets live in
# the repository's data/ folder, outside the context, and are mounted at run
# time. Images are safe to publish.

# python:3.12-slim (Debian trixie), pinned by digest for reproducible builds.
ARG PYTHON_IMAGE=python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f

FROM ${PYTHON_IMAGE} AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
RUN useradd --create-home --uid 10001 app \
 && mkdir -p /curated /traces \
 && chown app:app /curated /traces
WORKDIR /app

# Some networks block files.pythonhosted.org; point this at a mirror if so.
ARG PIP_INDEX_URL=https://pypi.org/simple

FROM base AS deps-web
COPY requirements-web.lock /tmp/requirements.lock
RUN python -m venv /opt/venv && /opt/venv/bin/pip install --index-url "$PIP_INDEX_URL" --require-hashes -r /tmp/requirements.lock

FROM base AS deps-insights
COPY requirements-insights.lock /tmp/requirements.lock
RUN python -m venv /opt/venv && /opt/venv/bin/pip install --index-url "$PIP_INDEX_URL" --require-hashes -r /tmp/requirements.lock

FROM base AS deps-ingest
COPY requirements-ingest.lock /tmp/requirements.lock
RUN python -m venv /opt/venv && /opt/venv/bin/pip install --index-url "$PIP_INDEX_URL" --require-hashes -r /tmp/requirements.lock

FROM base AS runtime
# The services listen on every interface inside the container; run directly, they default to 127.0.0.1.
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/app \
    BIND_HOST=0.0.0.0
COPY src/football_insights /app/football_insights
USER 10001

FROM runtime AS web
COPY --from=deps-web /opt/venv /opt/venv
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2)"]
LABEL org.opencontainers.image.title="football-insights-web" \
      org.opencontainers.image.description="Public web UI for the football insights demo" \
      org.opencontainers.image.licenses="MIT"
CMD ["python", "-m", "football_insights.web"]

FROM runtime AS insights
COPY --from=deps-insights /opt/venv /opt/venv
EXPOSE 8081
HEALTHCHECK --interval=15s --timeout=3s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8081/healthz', timeout=2)"]
LABEL org.opencontainers.image.title="football-insights-insights" \
      org.opencontainers.image.description="Internal analytics tools and insights agent for the football insights demo" \
      org.opencontainers.image.licenses="MIT"
CMD ["python", "-m", "football_insights.insights"]

FROM runtime AS ingest
COPY --from=deps-ingest /opt/venv /opt/venv
LABEL org.opencontainers.image.title="football-insights-ingest" \
      org.opencontainers.image.description="Batch job that verifies raw data and publishes a curated version" \
      org.opencontainers.image.licenses="MIT"
CMD ["python", "-m", "football_insights", "ingest"]
