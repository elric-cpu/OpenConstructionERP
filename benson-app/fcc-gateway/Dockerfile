FROM python:3.14-slim

RUN pip install --no-cache-dir free-claude-code==2.4.1 \
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
