FROM python:3.14-slim
WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .
RUN useradd --system --uid 10001 benson && mkdir -p /var/lib/benson/private-uploads && chown -R benson /var/lib/benson
USER benson
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
