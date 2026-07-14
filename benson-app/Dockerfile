FROM node:22-alpine AS web-build
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.14-slim
WORKDIR /app
RUN apt-get update \
  && apt-get install -y --no-install-recommends nginx \
  && rm -rf /var/lib/apt/lists/*
COPY api/pyproject.toml ./
COPY api/app ./app
RUN pip install --no-cache-dir .
COPY --from=web-build /web/dist /usr/share/nginx/html
COPY nginx.cloudrun.conf /etc/nginx/sites-enabled/default
RUN mkdir -p /var/lib/benson/private-uploads
ENV PORT=8080
CMD ["sh", "-c", "uvicorn app.main:app --host 127.0.0.1 --port 8000 & exec nginx -g 'daemon off;'"]
