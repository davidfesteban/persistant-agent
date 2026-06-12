import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
import websockets.sync.client


PROJECT_ROOT = Path(os.environ.get("PERSISTANT_AGENT_HOME", Path(__file__).resolve().parents[2]))
MACHINE_HOST = os.environ.get("PERSISTANT_MACHINE_HOST", "127.0.0.1")
MACHINE_PORT = int(os.environ.get("PERSISTANT_MACHINE_PORT", "8765"))
MACHINE_TOKEN = os.environ.get("PERSISTANT_MACHINE_TOKEN", "")
AGENT_CWD = "/workspace/repo"


class AgentStartRequest(BaseModel):
    repo_path: str = Field(min_length=1)


class MessageRequest(BaseModel):
    message: str = Field(min_length=1)
    thread_id: str | None = None
    model: str | None = None
    effort: str | None = None


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
    return AgentsResponse(agents=_list_agents())


@app.get("/agents/{name}", response_model=AgentInfo)
def get_agent(name: str) -> AgentInfo:
    return _get_agent_or_404(name)


@app.post("/agents/{name}/start", response_model=AgentInfo)
def start_agent(name: str, request: AgentStartRequest) -> AgentInfo:
    repo_path = Path(request.repo_path).expanduser().resolve()
    if not repo_path.is_dir():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Repository path does not exist")
    env = {
        **os.environ,
        "REPOSITORY_PATH": str(repo_path),
        "AGENT_NAME": name,
        "PERSISTANT_AGENT_WS_TOKEN": os.environ.get("PERSISTANT_AGENT_WS_TOKEN", secrets.token_urlsafe(32)),
    }
    _run(["docker", "compose", "-p", _project_name(name), "up", "-d", "--build"], env=env)
    return _wait_for_agent(name)


@app.post("/agents/{name}/stop")
def stop_agent(name: str) -> dict:
    env = {**os.environ, "REPOSITORY_PATH": str(PROJECT_ROOT), "AGENT_NAME": name}
    _run(["docker", "compose", "-p", _project_name(name), "down"], env=env)
    return {"stopped": name}


@app.post("/agents/{name}/messages")
def send_message(name: str, request: MessageRequest) -> dict:
    return _send_codex_turn(
        _get_agent_or_404(name),
        request.message,
        thread_id=request.thread_id,
        model=request.model,
        effort=request.effort,
    )


@app.post("/agents/{name}/files")
def send_files(name: str, request: FilesRequest) -> dict:
    agent = _get_agent_or_404(name)
    saved = [_write_repo_file(agent, file) for file in request.files]
    response: dict[str, Any] = {"files": saved}
    if request.message:
        paths = "\n".join(f"- {file['path']} ({file['bytes']} bytes, sha256 {file['sha256']})" for file in saved)
        response["message"] = _send_codex_turn(agent, f"{request.message}\n\nFiles saved:\n{paths}", thread_id=request.thread_id)
    return response


def _list_agents() -> list[AgentInfo]:
    agents = []
    for container in _docker_container_names():
        inspected = _inspect_container(container)
        if inspected is not None:
            agents.append(_agent_info(inspected))
    return sorted(agents, key=lambda agent: agent.name)


def _get_agent_or_404(name: str) -> AgentInfo:
    for agent in _list_agents():
        if agent.name == name:
            return agent
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")


def _wait_for_agent(name: str) -> AgentInfo:
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


def _docker_container_names() -> list[str]:
    result = _run(["docker", "ps", "-a", "--filter", "name=^/persistant-agent-", "--format", "{{.Names}}"])
    return [line for line in result.stdout.splitlines() if line.startswith("persistant-agent-")]


def _inspect_container(container: str) -> dict | None:
    result = subprocess.run(["docker", "inspect", container], cwd=PROJECT_ROOT, text=True, capture_output=True)
    if result.returncode != 0:
        return None
    return json.loads(result.stdout)[0]


def _agent_info(container: dict) -> AgentInfo:
    labels = container["Config"].get("Labels") or {}
    name = labels.get("persistant-agent.name") or container["Name"].removeprefix("/persistant-agent-")
    repo_path = labels.get("persistant-agent.repo")
    port = _host_port(container)
    api_url = f"http://127.0.0.1:{port}" if port is not None else None
    websocket_url = f"ws://127.0.0.1:{port}" if port is not None else None
    return AgentInfo(
        name=name,
        container=container["Name"].lstrip("/"),
        status=container["State"]["Status"],
        repo_path=repo_path,
        port=port,
        api_url=api_url,
        websocket_url=websocket_url,
    )


def _host_port(container: dict) -> int | None:
    ports = container["NetworkSettings"].get("Ports") or {}
    binding = (ports.get("8080/tcp") or [None])[0]
    return int(binding["HostPort"]) if binding else None


def _write_repo_file(agent: AgentInfo, file: FilePayload) -> dict:
    if agent.repo_path is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent has no repo path label")
    raw = Path(file.path)
    if raw.is_absolute() or ".." in raw.parts:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File paths must be repo-relative")
    try:
        content = base64.b64decode(file.content_base64, validate=True)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid base64 content") from exc
    repo = Path(agent.repo_path).resolve()
    destination = (repo / raw).resolve()
    if destination != repo and repo not in destination.parents:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File path escapes repository")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    return {"path": str(destination.relative_to(repo)), "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}


def _send_codex_turn(
    agent: AgentInfo,
    message: str,
    *,
    thread_id: str | None = None,
    model: str | None = None,
    effort: str | None = None,
) -> dict:
    if agent.websocket_url is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent has no websocket URL")
    headers = {}
    token = _agent_ws_token(agent.container)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with websockets.sync.client.connect(agent.websocket_url, additional_headers=headers, open_timeout=10, close_timeout=2) as websocket:
        client = CodexRpc(websocket)
        client.call(
            "initialize",
            {
                "clientInfo": {"name": "persistant-agent", "title": "Persistant Agent", "version": "0.1.0"},
                "capabilities": {"experimentalApi": True},
            },
        )
        client.notify("initialized", {})
        if thread_id is None:
            result = client.call(
                "thread/start",
                {
                    "cwd": AGENT_CWD,
                    "model": model,
                    "approvalPolicy": "never",
                    "sandbox": "danger-full-access",
                    "ephemeral": False,
                },
            )
            thread_id = result["thread"]["id"]
        params: dict[str, Any] = {"threadId": thread_id, "cwd": AGENT_CWD, "input": [{"type": "text", "text": message}]}
        if model:
            params["model"] = model
        if effort:
            params["effort"] = effort
        client.call("turn/start", params)
        return client.read_turn(thread_id)


class CodexRpc:
    def __init__(self, websocket):
        self.websocket = websocket
        self.next_id = 1
        self.pending: list[dict] = []

    def call(self, method: str, params: dict) -> dict:
        request_id = self.next_id
        self.next_id += 1
        self.websocket.send(json.dumps({"id": request_id, "method": method, "params": params}))
        while True:
            message = self._recv()
            if message.get("id") != request_id:
                self.pending.append(message)
                continue
            if "error" in message:
                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=message["error"])
            return message.get("result") or {}

    def notify(self, method: str, params: dict) -> None:
        self.websocket.send(json.dumps({"method": method, "params": params}))

    def read_turn(self, thread_id: str) -> dict:
        events: list[dict] = []
        text: list[str] = []
        while True:
            message = self.pending.pop(0) if self.pending else self._recv()
            method = message.get("method", "")
            params = message.get("params") or {}
            events.append(message)
            if method == "item/agentMessage/delta":
                text.append(params.get("delta", ""))
            if method == "turn/completed":
                return {"thread_id": thread_id, "text": "".join(text), "events": events}
            if method == "error":
                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=params)

    def _recv(self) -> dict:
        return json.loads(self.websocket.recv())


def _http_ok(url: str) -> bool:
    try:
        result = subprocess.run(["curl", "-fsS", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
    except subprocess.TimeoutExpired:
        return False
    return result.returncode == 0


def _agent_ws_token(container: str) -> str | None:
    inspected = _inspect_container(container)
    if inspected is None:
        return None
    for entry in inspected["Config"].get("Env") or []:
        if entry.startswith("CODEX_WS_TOKEN="):
            return entry.removeprefix("CODEX_WS_TOKEN=")
    return None


def _project_name(name: str) -> str:
    return f"persistant-agent-{name}"


def _run(command: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
    result = subprocess.run(command, cwd=PROJECT_ROOT, env=env, text=True, capture_output=True)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)
    return result


WEB_UI = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Persistant Agents</title>
<style>
body{font:14px system-ui,sans-serif;margin:0;color:#18181b;background:#fafafa}
main{display:grid;grid-template-columns:300px 1fr;min-height:100vh}
aside{border-right:1px solid #ddd;background:white;padding:14px}
section{padding:14px;display:grid;grid-template-rows:auto 1fr auto;gap:10px}
h1{font-size:18px;margin:0 0 10px}button,input,textarea{font:inherit}
button{border:1px solid #bbb;background:white;padding:7px 10px;cursor:pointer;border-radius:6px}
.agent{display:block;width:100%;text-align:left;margin:6px 0}.meta{color:#666;font-size:12px;overflow-wrap:anywhere}
textarea{width:100%;min-height:90px;box-sizing:border-box}input[type=text]{flex:1;min-width:0;padding:7px}
#log{background:#111;color:#f4f4f5;padding:12px;overflow:auto;white-space:pre-wrap;border-radius:6px}.row{display:flex;gap:8px;align-items:center}
</style>
</head>
<body>
<main>
<aside><div class="row"><h1>Agents</h1><button onclick="loadAgents()">Refresh</button></div><div id="agents"></div></aside>
<section>
<div><strong id="selected">Select an agent</strong><div class="meta" id="endpoint"></div></div>
<pre id="log"></pre>
<div>
<textarea id="message" placeholder="Message to Codex"></textarea>
<div class="row">
<button onclick="sendMessage()">Send</button>
<input id="filePath" type="text" placeholder="repo-relative destination">
<input id="file" type="file">
<button onclick="sendFile()">Upload</button>
</div>
</div>
</section>
</main>
<script>
let current=null, threads={};
const log=document.getElementById('log');
function write(x){log.textContent+=x+'\\n';log.scrollTop=log.scrollHeight}
async function json(url,options){const r=await fetch(url,options);const x=await r.json();if(!r.ok)throw new Error(JSON.stringify(x));return x}
async function loadAgents(){
  const data=await json('/agents'); const root=document.getElementById('agents'); root.innerHTML='';
  data.agents.forEach(agent=>{
    const b=document.createElement('button'); b.className='agent';
    b.innerHTML=`<strong>${agent.name}</strong><span class="meta">${agent.status} - ${agent.api_url||'no port'}</span>`;
    b.onclick=()=>select(agent); root.appendChild(b);
  });
}
function select(agent){current=agent;log.textContent='';document.getElementById('selected').textContent=agent.name;document.getElementById('endpoint').textContent=agent.websocket_url||''}
async function sendMessage(){
  if(!current)return write('No selected agent');
  const message=document.getElementById('message').value.trim(); if(!message)return;
  document.getElementById('message').value=''; write('> '+message);
  try{const r=await json(`/agents/${current.name}/messages`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({message,thread_id:threads[current.name]})});
    threads[current.name]=r.thread_id; write(r.text||JSON.stringify(r));
  }catch(e){write(e.message)}
}
async function sendFile(){
  if(!current)return write('No selected agent');
  const file=document.getElementById('file').files[0], path=document.getElementById('filePath').value.trim();
  if(!file||!path)return write('Choose a file and destination path');
  const bytes=new Uint8Array(await file.arrayBuffer()); let bin=''; bytes.forEach(b=>bin+=String.fromCharCode(b));
  try{const r=await json(`/agents/${current.name}/files`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({files:[{path,content_base64:btoa(bin)}],thread_id:threads[current.name],message:document.getElementById('message').value.trim()||null})});
    if(r.message)threads[current.name]=r.message.thread_id; write(JSON.stringify(r,null,2));
  }catch(e){write(e.message)}
}
loadAgents();
</script>
</body>
</html>"""
