# syntax=docker/dockerfile:1
FROM node:24-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS wheels
WORKDIR /build
COPY backend/ ./
RUN pip wheel --no-cache-dir --wheel-dir /wheels .

FROM python:3.12-slim-bookworm
ARG PUID=1000
ARG PGID=1000
RUN groupadd -g ${PGID} magpie && useradd -u ${PUID} -g magpie -M -s /usr/sbin/nologin magpie \
    && mkdir -p /config /downloads && chown magpie:magpie /config /downloads
COPY --from=wheels /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels magpie-nas && rm -rf /wheels
WORKDIR /app
COPY --from=frontend --chown=magpie:magpie /build/dist /app/static
ENV MAGPIE_CONFIG=/config MAGPIE_STATIC=/app/static PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER magpie
EXPOSE 9080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9080/api/health', timeout=3)"]
CMD ["python", "-m", "app"]
COPY LICENSE COPYING /app/licenses/
