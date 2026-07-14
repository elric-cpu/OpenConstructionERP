FROM node:22-alpine AS web-build
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.14-slim
WORKDIR /app
COPY api/pyproject.toml ./
COPY api/app ./app
RUN pip install --no-cache-dir .
COPY skills ./skills
COPY --from=web-build /web/dist /app/web-dist
RUN useradd --system --uid 10001 benson \
    && mkdir -p /var/lib/benson/private-uploads \
    && chown -R benson:benson /var/lib/benson /app
ENV PORT=8080
ENV BENSON_WEB_DIST_PATH=/app/web-dist
USER benson
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
