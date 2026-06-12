import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from persistant_agent.agent_runtime import PROJECT_ROOT


@dataclass(frozen=True)
class AgentRecord:
    name: str
    container: str
    status: str
    repo_path: str | None
    port: int | None
    api_url: str | None
    websocket_url: str | None


def project_name(name: str) -> str:
    return f"persistant-agent-{name}"


def list_agent_records() -> list[AgentRecord]:
    records = []
    for container in _container_names():
        inspected = inspect_container(container)
        if inspected is not None:
            records.append(agent_record(inspected))
    return sorted(records, key=lambda item: item.name)


def get_agent_record(name: str) -> AgentRecord | None:
    for record in list_agent_records():
        if record.name == name:
            return record
    return None


def inspect_container(container: str) -> dict | None:
    result = subprocess.run(["docker", "inspect", container], cwd=PROJECT_ROOT, text=True, capture_output=True)
    if result.returncode != 0:
        return None
    return json.loads(result.stdout)[0]


def agent_record(container: dict) -> AgentRecord:
    labels = container["Config"].get("Labels") or {}
    name = labels.get("persistant-agent.name") or container["Name"].removeprefix("/persistant-agent-")
    repo_path = labels.get("persistant-agent.repo")
    port = host_port(container)
    api_url = f"http://127.0.0.1:{port}" if port is not None else None
    websocket_url = f"ws://127.0.0.1:{port}" if port is not None else None
    return AgentRecord(
        name=name,
        container=container["Name"].lstrip("/"),
        status=container["State"]["Status"],
        repo_path=repo_path,
        port=port,
        api_url=api_url,
        websocket_url=websocket_url,
    )


def agent_ws_token(container: str) -> str | None:
    inspected = inspect_container(container)
    if inspected is None:
        return None
    for entry in inspected["Config"].get("Env") or []:
        if entry.startswith("CODEX_WS_TOKEN="):
            return entry.removeprefix("CODEX_WS_TOKEN=")
    return None


def host_port(container: dict) -> int | None:
    ports = container["NetworkSettings"].get("Ports") or {}
    binding = (ports.get("8080/tcp") or [None])[0]
    return int(binding["HostPort"]) if binding else None


def _container_names() -> list[str]:
    result = subprocess.run(
        ["docker", "ps", "-a", "--filter", "name=^/persistant-agent-", "--format", "{{.Names}}"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line.startswith("persistant-agent-")]
