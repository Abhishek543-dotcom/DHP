FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/home/app/.local/bin:${PATH}"

RUN groupadd -r app && useradd -r -g app -d /home/app -m -s /sbin/nologin app

WORKDIR /app
COPY --from=builder /root/.local /home/app/.local
COPY --chown=app:app . /app

USER app

CMD ["python", "-m", "app.main"]
