FROM node:22-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git openssh-client \
    && npm install -g @openai/codex@0.139.0 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace/repo

EXPOSE 8080

CMD ["/bin/sh", "-lc", "printf '%s' \"${CODEX_WS_TOKEN:-persistant-agent-local-token}\" > /tmp/codex-ws-token && chmod 600 /tmp/codex-ws-token && exec codex app-server --listen ws://0.0.0.0:8080 --ws-auth capability-token --ws-token-file /tmp/codex-ws-token -c sandbox_mode=\\\"danger-full-access\\\" -c approval_policy=\\\"never\\\""]
