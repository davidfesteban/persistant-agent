import os
import secrets
import time
from typing import Annotated, Any
import urllib.error
import urllib.request

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from persistant_agent.agent_runtime import PROJECT_ROOT, WS_TOKEN_ENV
from persistant_agent.codex_rpc import send_turn
from persistant_agent.docker_registry import AgentRecord, get_agent_record, list_agent_records, project_name
from persistant_agent.file_bridge import write_repo_file
from persistant_agent.web_ui import WEB_UI
import subprocess
from pathlib import Path


MACHINE_TOKEN = os.environ.get("PERSISTANT_MACHINE_TOKEN", "")


class AgentStartRequest(BaseModel):
    repo_path: str = Field(min_length=1)


class MessageRequest(BaseModel):
    message: str = Field(min_length=1)
    thread_id: str | None = None


class FilePayload(BaseModel):
    path: str = Field(min_length=1)
    content_base64: str


class FilesRequest(BaseModel):
    files: list[FilePayload] = Field(min_length=1)
    message: str | None = None
    thread_id: str | None = None


class AgentInfo(BaseModel):
    name: str
    container: str
    status: str
    repo_path: str | None = None
    port: int | None = None
    api_url: str | None = None
    websocket_url: str | None = None


class AgentsResponse(BaseModel):
    agents: list[AgentInfo]


def require_token(authorization: Annotated[str | None, Header()] = None) -> None:
    if MACHINE_TOKEN and authorization != f"Bearer {MACHINE_TOKEN}":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


app = FastAPI(title="Persistant Agent Machine API", version="0.1.0", dependencies=[Depends(require_token)])


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def get_web_ui() -> str:
    return WEB_UI


@app.get("/health")
def get_health() -> dict:
    return {"status": "ok"}


@app.get("/agents", response_model=AgentsResponse)
def list_agents() -> AgentsResponse:
    return AgentsResponse(agents=[_agent_info(record) for record in list_agent_records()])


@app.get("/agents/{name}", response_model=AgentInfo)
def get_agent(name: str) -> AgentInfo:
    return _agent_info(_get_agent_or_404(name))


@app.post("/agents/{name}/start", response_model=AgentInfo)
def start_agent(name: str, request: AgentStartRequest) -> AgentInfo:
    repo_path = Path(request.repo_path).expanduser().resolve()
    if not repo_path.is_dir():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Repository path does not exist")
    env = {
        **os.environ,
        "REPOSITORY_PATH": str(repo_path),
        "AGENT_NAME": name,
        WS_TOKEN_ENV: os.environ.get(WS_TOKEN_ENV, secrets.token_urlsafe(32)),
    }
    _run(["docker", "compose", "-p", project_name(name), "up", "-d", "--build"], env=env)
    return _agent_info(_wait_for_agent(name))


@app.post("/agents/{name}/stop")
def stop_agent(name: str) -> dict:
    env = {**os.environ, "REPOSITORY_PATH": str(PROJECT_ROOT), "AGENT_NAME": name}
    _run(["docker", "compose", "-p", project_name(name), "down"], env=env)
    return {"stopped": name}


@app.post("/agents/{name}/messages")
def send_message(name: str, request: MessageRequest) -> dict:
    return send_turn(_get_agent_or_404(name), request.message, thread_id=request.thread_id)


@app.post("/agents/{name}/files")
def send_files(name: str, request: FilesRequest) -> dict:
    agent = _get_agent_or_404(name)
    saved = [write_repo_file(agent, file.path, file.content_base64) for file in request.files]
    response: dict[str, Any] = {"files": saved}
    if request.message:
        paths = "\n".join(f"- {file['path']} ({file['bytes']} bytes, sha256 {file['sha256']})" for file in saved)
        response["message"] = send_turn(agent, f"{request.message}\n\nFiles saved:\n{paths}", thread_id=request.thread_id)
    return response


def _get_agent_or_404(name: str) -> AgentRecord:
    agent = get_agent_record(name)
    if agent is not None:
        return agent
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")


def _wait_for_agent(name: str) -> AgentRecord:
    last_agent = None
    for _ in range(30):
        try:
            last_agent = _get_agent_or_404(name)
            if last_agent.api_url and _http_ok(f"{last_agent.api_url}/readyz"):
                return last_agent
        except HTTPException:
            pass
        time.sleep(1)
    if last_agent is not None:
        return last_agent
    raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Agent did not start")


def _agent_info(agent: AgentRecord) -> AgentInfo:
    return AgentInfo(
        name=agent.name,
        container=agent.container,
        status=agent.status,
        repo_path=agent.repo_path,
        port=agent.port,
        api_url=agent.api_url,
        websocket_url=agent.websocket_url,
    )


def _http_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return response.status == 200
    except (OSError, TimeoutError, urllib.error.URLError):
        return False


def _run(command: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
    result = subprocess.run(command, cwd=PROJECT_ROOT, env=env, text=True, capture_output=True)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)
    return result
