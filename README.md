# Persistant Agent

Run one Codex agent per repository, keep them alive in Docker, and talk to them from one small machine UI.

Persistant Agent is a tiny local control plane for multi-repo development. The host machine owns lifecycle and discovery. Each container owns exactly one job: bind a repository and run `codex app-server` inside it.

## Why

Contract-first backend work gets slow when every repository lives in a different terminal, context window, or Codex session. This project keeps those repo agents running side by side so another tool, another agent, or you from the browser can send work to the right repository without manually switching shells.

The intended shape is simple:

```text
browser / API
    |
    v
machine FastAPI server
    |       \
    |        \__ Docker state registry
    |
    v
agent container per repo
    |
    v
codex app-server in /workspace/repo
```

## What It Does

- Starts one Docker container per repository.
- Binds your repo into `/workspace/repo`.
- Binds your local Codex auth/config and git credentials read-only.
- Runs `codex app-server` in the container.
- Exposes a machine WebUI at `http://127.0.0.1:8765`.
- Lets the WebUI send JSON-RPC/WebSocket messages to an agent.
- Discovers running agents from Docker state. No database.

## What It Does Not Do

- No custom agent protocol.
- No REST `/messages` endpoint.
- No file-transfer API.
- No token/auth layer inside this project.
- No duplicate registry inside every container.

Services are expected to run on your trusted machine or behind your VPN.

## Requirements

- Docker
- Docker Compose
- Python 3.12+
- Local Codex login in `~/.codex`
- Git credentials available on the host

## Quick Start

Start the machine UI:

```sh
make machine
```

Open:

```text
http://127.0.0.1:8765
```

Start an agent for a repo:

```sh
make start /Users/you/Repositories/backend backend
```

Stop it:

```sh
make stop backend
```

List agents through the machine API:

```sh
make agents
```

## Model Defaults

Agents start with:

```text
model = gpt-5.5
model_reasoning_effort = medium
```

Override per start:

```sh
make start /Users/you/Repositories/backend backend MODEL=gpt-5.5 REASONING_EFFORT=high
```

Existing containers keep their original startup config. Recreate an agent to change it:

```sh
make stop backend
make start /Users/you/Repositories/backend backend MODEL=gpt-5.5 REASONING_EFFORT=high
```

## Machine API

The machine server is intentionally small:

```text
GET  /
GET  /agents
GET  /agents/{name}
POST /agents/{name}/start
POST /agents/{name}/stop
WS   /agents/{name}/ws
```

`/agents/{name}/ws` is a same-origin WebSocket proxy to the agent container. The browser talks to the machine; the machine talks to Codex App Server.

This matters because Codex App Server rejects browser WebSocket requests that include an `Origin` header. The proxy keeps the WebUI simple while leaving the agent container as plain Codex App Server.

## Container Shape

Each agent container receives:

```text
AGENT_NAME
REPOSITORY_PATH
CODEX_MODEL
CODEX_REASONING_EFFORT
```

Mounted into the container:

```text
repo                 -> /workspace/repo
~/.codex/auth.json   -> /root/.codex/auth.json
~/.codex/config.toml -> /root/.codex/config.toml
~/.codex/AGENTS.md   -> /root/.codex/AGENTS.md
~/.gitconfig         -> /root/.gitconfig
~/.ssh               -> /root/.ssh
```

The container listens on a random localhost port. The machine API reports the resolved URL.

## Development

Install dependencies:

```sh
python3.12 -m venv .venv
.venv/bin/pip install -e '.[test]'
```

Run tests:

```sh
.venv/bin/python -m pytest -q
```

Check Docker Compose:

```sh
REPOSITORY_PATH=/tmp AGENT_NAME=demo docker compose config --quiet
```

## Design Rule

Keep it boring.

The source of truth is Docker state. The transport is Codex App Server JSON-RPC over WebSocket. The host is only lifecycle, discovery, and the browser bridge.
