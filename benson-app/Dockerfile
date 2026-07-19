FROM ghcr.io/astral-sh/uv:0.11.26@sha256:3d868e555f8f1dbc324afa005066cd11e1053fc4743b9808ca8025283e65efa5 AS uv

FROM node:22-alpine@sha256:16e22a550f3863206a3f701448c45f7912c6896a62de43add43bb9c86130c3e2 AS web-build
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de
WORKDIR /app
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_CACHE_DIR=/tmp/uv-cache
RUN useradd --system --uid 10001 benson \
    && mkdir -p /var/lib/benson/private-uploads \
    && chown benson:benson /app /var/lib/benson /var/lib/benson/private-uploads
COPY --chown=10001:10001 api/pyproject.toml api/uv.lock ./
USER benson
RUN uv sync --frozen --no-dev --no-install-project \
    && rm -rf "$UV_CACHE_DIR"
COPY --chown=10001:10001 api/app ./app
RUN uv sync --frozen --no-dev --no-editable \
    && rm -rf "$UV_CACHE_DIR"
COPY --chown=10001:10001 api/migrations ./migrations
COPY --chown=10001:10001 skills ./skills
COPY --chown=10001:10001 --from=web-build /web/dist /app/web-dist
ENV PORT=8080
ENV BENSON_WEB_DIST_PATH=/app/web-dist
ENV PATH="/app/.venv/bin:$PATH"
ARG VCS_REF=unknown
LABEL org.opencontainers.image.revision="$VCS_REF"
LABEL org.opencontainers.image.source="https://github.com/elric-cpu/OpenConstructionERP"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
