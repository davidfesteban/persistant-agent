from contextlib import asynccontextmanager
import asyncio
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field
import yaml

from persistant_agent.codex_session import CodexSession
from persistant_agent.config import Settings, get_settings


class HealthResponse(BaseModel):
    status: Literal["ok"]
    codex_running: bool


class SessionResponse(BaseModel):
    running: bool
    target_repo: str
    command: list[str]
    pid: int | None


class ModelSelectRequest(BaseModel):
    model: str = Field(min_length=1)
    effort: Literal["minimal", "low", "medium", "high"] | None = None


class MessageRequest(BaseModel):
    message: str = Field(min_length=1)


class ContextRequest(BaseModel):
    action: Literal["empty", "compact"]


class CommandResponse(BaseModel):
    accepted: bool
    sent: list[str]


class ServiceInfoResponse(BaseModel):
    name: str
    version: str
    openapi_url: str
    docs_url: str
    websocket_url: str
    commands: dict[str, str]
    websocket_commands: dict[str, str]


def require_token(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    if not settings.api_token:
        return
    expected = f"Bearer {settings.api_token}"
    if authorization != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


settings = get_settings()
session = CodexSession(settings.codex_argv, settings.target_repo)


@asynccontextmanager
async def lifespan(_: FastAPI):
    session.start()
    yield


app = FastAPI(
    title="Persistant Agent API",
    version="0.1.0",
    lifespan=lifespan,
    dependencies=[Depends(require_token)],
)
OPENAPI_PATH = Path(__file__).resolve().parents[2] / "openapi.yaml"


@lru_cache
def openapi_schema() -> dict:
    return yaml.safe_load(OPENAPI_PATH.read_text())


app.openapi = openapi_schema


@app.get("/", response_model=ServiceInfoResponse)
def get_service_info() -> ServiceInfoResponse:
    return ServiceInfoResponse(
        name="Persistant Agent API",
        version="0.1.0",
        openapi_url="/openapi.json",
        docs_url="/docs",
        websocket_url="/ws",
        commands={
            "health": "GET /health",
            "session": "GET /session",
            "select_model": "POST /session/model",
            "send_message": "POST /messages",
            "update_context": "POST /context",
        },
        websocket_commands={
            "message": '{"type":"message","message":"text"}',
            "select_model": '{"type":"model","model":"gpt-5","effort":"high"}',
            "update_context": '{"type":"context","action":"compact"}',
        },
    )


@app.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    return HealthResponse(status="ok", codex_running=session.state().running)


@app.get("/session", response_model=SessionResponse)
def get_session() -> SessionResponse:
    return SessionResponse.model_validate(session.state().__dict__)


@app.post("/session/model", status_code=status.HTTP_202_ACCEPTED, response_model=CommandResponse)
def select_model(request: ModelSelectRequest) -> CommandResponse:
    lines = [settings.model_command_template.format(model=request.model)]
    if request.effort is not None:
        lines.append(settings.effort_command_template.format(effort=request.effort))
    sent = session.send_lines(lines)
    return CommandResponse(accepted=True, sent=sent)


@app.post("/messages", status_code=status.HTTP_202_ACCEPTED, response_model=CommandResponse)
def send_message(request: MessageRequest) -> CommandResponse:
    sent = session.send_lines([request.message])
    return CommandResponse(accepted=True, sent=sent)


@app.post("/context", status_code=status.HTTP_202_ACCEPTED, response_model=CommandResponse)
def update_context(request: ContextRequest) -> CommandResponse:
    command = settings.clear_command if request.action == "empty" else settings.compact_command
    sent = session.send_lines([command])
    return CommandResponse(accepted=True, sent=sent)


@app.websocket("/ws")
async def websocket_session(websocket: WebSocket) -> None:
    await websocket.accept()
    session.start()
    state = session.state()
    await websocket.send_json(
        {
            "type": "ready",
            "running": state.running,
            "target_repo": state.target_repo,
            "pid": state.pid,
        }
    )
    last_seq = 0
    while True:
        try:
            message = await asyncio.wait_for(websocket.receive_json(), timeout=0.1)
            sent = _handle_websocket_command(message)
            await websocket.send_json({"type": "ack", "sent": sent})
        except TimeoutError:
            pass
        except WebSocketDisconnect:
            return
        except Exception as exc:
            await websocket.send_json({"type": "error", "detail": str(exc)})

        events = await asyncio.to_thread(session.wait_for_output, last_seq, 0.1)
        for event in events:
            last_seq = max(last_seq, event.seq)
            await websocket.send_json(
                {
                    "type": event.type,
                    "seq": event.seq,
                    "data": event.data,
                }
            )


def _handle_websocket_command(message: dict) -> list[str]:
    command_type = message.get("type")
    if command_type == "message":
        request = MessageRequest.model_validate(message)
        return session.send_lines([request.message])
    if command_type == "model":
        request = ModelSelectRequest.model_validate(message)
        lines = [settings.model_command_template.format(model=request.model)]
        if request.effort is not None:
            lines.append(settings.effort_command_template.format(effort=request.effort))
        return session.send_lines(lines)
    if command_type == "context":
        request = ContextRequest.model_validate(message)
        command = settings.clear_command if request.action == "empty" else settings.compact_command
        return session.send_lines([command])
    raise ValueError("Unsupported websocket command type")
