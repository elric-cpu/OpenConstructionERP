FROM python:3.14-slim

RUN pip install --no-cache-dir \
      https://github.com/Alishahryar1/free-claude-code/archive/6a48811a9a648110c894738ee62dcb48b69cef96.tar.gz \
    && useradd --create-home --system --uid 10001 fcc \
    && mkdir -p /home/fcc/.fcc \
    && chown -R fcc:fcc /home/fcc

ENV HOME=/home/fcc
ENV PORT=8080
ENV FCC_OPEN_BROWSER=false
ENV MESSAGING_PLATFORM=none
ENV ENABLE_WEB_SERVER_TOOLS=false
ENV LOG_RAW_API_PAYLOADS=false
ENV LOG_RAW_SSE_EVENTS=false
ENV LOG_API_ERROR_TRACEBACKS=false

USER fcc
CMD ["fcc-server"]
