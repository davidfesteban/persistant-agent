FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates npm \
    && npm install -g @openai/codex@0.139.0 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY openapi.yaml .
COPY src ./src

EXPOSE 8080

CMD ["uvicorn", "persistant_agent.api:app", "--host", "0.0.0.0", "--port", "8080"]
