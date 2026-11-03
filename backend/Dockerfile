FROM python:3.12-slim-bookworm AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml constraints.txt ./
COPY src ./src
RUN pip install -c constraints.txt . && useradd --uid 10001 --create-home app
COPY alembic.ini logging.json ./
COPY migrations ./migrations
ARG APP_VERSION=dev
ARG RELEASE_ID=local
ENV APP_VERSION=${APP_VERSION} RELEASE_ID=${RELEASE_ID}
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
  CMD ["/usr/bin/env", "-i", "PATH=/usr/local/bin:/usr/bin:/bin", "python", "-c", "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/api/health', timeout=3)"]
CMD ["python", "-m", "customer_orders.start"]

FROM base AS test
USER root
RUN pip install -c constraints.txt '.[dev]'
COPY tests ./tests
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]

FROM base AS runtime
