FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DUVO_LOG_DIR=/var/log/duvo

WORKDIR /app

RUN groupadd --system duvo && \
    useradd --system --gid duvo --home-dir /app duvo

COPY pyproject.toml README.md ./
COPY duvo ./duvo

RUN python -m pip install --no-cache-dir . && \
    mkdir -p /var/log/duvo && \
    chown -R duvo:duvo /app /var/log/duvo

USER duvo

CMD ["python", "-m", "duvo.mcp_server"]
