FROM node:22-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git openssh-client \
    && npm install -g @openai/codex@0.139.0 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace/repo

EXPOSE 8080
