import json
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.request

from pydantic import BaseModel


ROOT = Path(os.environ.get("PERSISTANT_AGENT_HOME", Path(__file__).resolve().parents[2]))


class Agent(BaseModel):
    name: str
    container: str
    status: str
    repo_path: str | None = None
    model: str | None = None
    reasoning_effort: str | None = None
    port: int | None = None
    api_url: str | None = None
    websocket_url: str | None = None


def list_agents() -> list[Agent]:
    result = run(["docker", "ps", "-a", "--filter", "name=^/persistant-agent-", "--format", "{{.Names}}"])
    agents = []
    for name in result.stdout.splitlines():
        if name.startswith("persistant-agent-") and (container := inspect(name)):
            agents.append(agent_from_container(container))
    return agents


def get_agent(name: str) -> Agent | None:
    return next((agent for agent in list_agents() if agent.name == name), None)


def start_agent(
    name: str,
    repo_path: str,
    model: str = "gpt-5.5",
    reasoning_effort: str = "medium",
) -> None:
    repo = Path(repo_path).expanduser().resolve()
    run(
        ["docker", "compose", "-p", project(name), "up", "-d", "--build"],
        env={
            **os.environ,
            "AGENT_NAME": name,
            "REPOSITORY_PATH": str(repo),
            "CODEX_MODEL": model,
            "CODEX_REASONING_EFFORT": reasoning_effort,
        },
    )


def stop_agent(name: str) -> None:
    run(["docker", "compose", "-p", project(name), "down"], env={**os.environ, "AGENT_NAME": name, "REPOSITORY_PATH": str(ROOT)})


def agent_ready(agent: Agent) -> bool:
    if not agent.api_url:
        return False
    try:
        with urllib.request.urlopen(f"{agent.api_url}/readyz", timeout=2) as response:
            return response.status == 200
    except (OSError, TimeoutError, urllib.error.URLError):
        return False


def agent_from_container(container: dict) -> Agent:
    labels = container["Config"].get("Labels") or {}
    env = container["Config"].get("Env") or []
    port = host_port(container)
    return Agent(
        name=labels.get("persistant-agent.name") or container["Name"].removeprefix("/persistant-agent-"),
        container=container["Name"].lstrip("/"),
        status=container["State"]["Status"],
        repo_path=labels.get("persistant-agent.repo"),
        model=labels.get("persistant-agent.model") or env_value(env, "CODEX_MODEL"),
        reasoning_effort=labels.get("persistant-agent.reasoning_effort") or env_value(env, "CODEX_REASONING_EFFORT"),
        port=port,
        api_url=f"http://127.0.0.1:{port}" if port else None,
        websocket_url=f"ws://127.0.0.1:{port}" if port else None,
    )


def inspect(container: str) -> dict | None:
    result = subprocess.run(["docker", "inspect", container], cwd=ROOT, text=True, capture_output=True)
    if result.returncode != 0:
        return None
    return json.loads(result.stdout)[0]


def host_port(container: dict) -> int | None:
    binding = ((container["NetworkSettings"].get("Ports") or {}).get("8080/tcp") or [None])[0]
    return int(binding["HostPort"]) if binding else None


def env_value(env: list[str], name: str) -> str | None:
    prefix = f"{name}="
    return next((value.removeprefix(prefix) for value in env if value.startswith(prefix)), None)


def project(name: str) -> str:
    return f"persistant-agent-{name}"


def run(command: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, check=False)
