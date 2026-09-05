FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
RUN mkdir -p apps/api/app \
    && touch apps/api/app/__init__.py \
    && pip install --no-cache-dir .
COPY alembic.ini ./
COPY apps/api ./apps/api
RUN groupadd --system benson \
    && useradd --system --gid benson --home-dir /nonexistent --shell /usr/sbin/nologin benson
ENV PYTHONPATH=/app/apps/api
USER benson
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
