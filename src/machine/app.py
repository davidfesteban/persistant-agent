import asyncio
import time
from pathlib import Path

import websockets
from websockets.exceptions import ConnectionClosed
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from machine import docker


class AgentStart(BaseModel):
    repo_path: str = Field(min_length=1)
    model: str = "gpt-5.5"
    reasoning_effort: str = "medium"


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


@app.websocket("/agents/{name}/ws")
async def agent_websocket(websocket: WebSocket, name: str) -> None:
    try:
        agent = _agent(name)
    except HTTPException:
        await websocket.close(code=1008)
        return
    if not agent.websocket_url:
        await websocket.close(code=1011)
        return

    await websocket.accept()
    try:
        async with websockets.connect(agent.websocket_url) as codex:
            browser_to_codex = asyncio.create_task(_browser_to_codex(websocket, codex))
            codex_to_browser = asyncio.create_task(_codex_to_browser(websocket, codex))
            done, pending = await asyncio.wait(
                {browser_to_codex, codex_to_browser},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                if task.cancelled():
                    continue
                error = task.exception()
                if error and not isinstance(error, WebSocketDisconnect):
                    raise error
    except ConnectionClosed:
        pass


@app.post("/agents/{name}/start", response_model=docker.Agent)
def start_agent(name: str, request: AgentStart) -> docker.Agent:
    repo = Path(request.repo_path).expanduser().resolve()
    if not repo.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Repository path does not exist",
        )
    docker.start_agent(
        name,
        str(repo),
        model=request.model,
        reasoning_effort=request.reasoning_effort,
    )
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


async def _browser_to_codex(websocket: WebSocket, codex) -> None:
    while True:
        await codex.send(await websocket.receive_text())


async def _codex_to_browser(websocket: WebSocket, codex) -> None:
    async for message in codex:
        await websocket.send_text(message)
