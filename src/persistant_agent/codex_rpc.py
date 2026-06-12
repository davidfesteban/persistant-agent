import json

from fastapi import HTTPException, status
import websockets.sync.client

from persistant_agent.agent_runtime import AGENT_CWD
from persistant_agent.docker_registry import AgentRecord, agent_ws_token


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


def send_turn(agent: AgentRecord, message: str, *, thread_id: str | None = None) -> dict:
    if agent.websocket_url is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent has no websocket URL")
    headers = {}
    token = agent_ws_token(agent.container)
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
                    "approvalPolicy": "never",
                    "sandbox": "danger-full-access",
                    "ephemeral": False,
                },
            )
            thread_id = result["thread"]["id"]
        client.call("turn/start", {"threadId": thread_id, "cwd": AGENT_CWD, "input": [{"type": "text", "text": message}]})
        return client.read_turn(thread_id)
