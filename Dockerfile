FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY config ./config
COPY src ./src

# data/ (the journal database) and logs/ are mounted from the VPS so they survive redeploys
RUN mkdir -p data logs

# Default job = the paper-trading bot. The dashboard service overrides this command in docker-compose.yml.
CMD ["python", "-m", "trading_bot", "run"]
