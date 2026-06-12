import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from machine import docker


class AgentStart(BaseModel):
    repo_path: str = Field(min_length=1)


app = FastAPI(title="Persistant Agent Machine", version="0.1.0")


@app.get("/")
def root() -> HTMLResponse:
    return HTMLResponse((Path(__file__).with_name("index.html")).read_text())


@app.get("/agents")
def agents() -> dict:
    return {"agents": docker.list_agents()}


@app.get("/agents/{name}", response_model=docker.Agent)
def get_agent(name: str) -> docker.Agent:
    return _agent(name)


@app.post("/agents/{name}/start", response_model=docker.Agent)
def start_agent(name: str, request: AgentStart) -> docker.Agent:
    repo = Path(request.repo_path).expanduser().resolve()
    if not repo.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Repository path does not exist",
        )
    docker.start_agent(name, str(repo))
    return _wait(name)


@app.post("/agents/{name}/stop")
def stop_agent(name: str) -> dict:
    docker.stop_agent(name)
    return {"stopped": name}


def _agent(name: str) -> docker.Agent:
    agent = docker.get_agent(name)
    if agent:
        return agent
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")


def _wait(name: str) -> docker.Agent:
    last = None
    for _ in range(30):
        try:
            last = _agent(name)
            if docker.agent_ready(last):
                return last
        except HTTPException:
            pass
        time.sleep(1)
    if last:
        return last
    raise HTTPException(
        status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Agent did not start"
    )
