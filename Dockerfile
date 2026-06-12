FROM node:22-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git openssh-client socat \
    && npm install -g @openai/codex@0.139.0 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY src/agent/entrypoint.sh /usr/local/bin/agent-entrypoint
RUN chmod +x /usr/local/bin/agent-entrypoint

WORKDIR /workspace/repo

EXPOSE 8080

CMD ["/usr/local/bin/agent-entrypoint"]
