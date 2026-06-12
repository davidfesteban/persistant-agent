import base64
import json

from fastapi import HTTPException
from fastapi.testclient import TestClient

from persistant_agent import codex_rpc, docker_registry
from persistant_agent import machine_api


def test_agent_info_from_docker_inspect():
    container = {
        "Name": "/persistant-agent-backend",
        "Config": {"Labels": {"persistant-agent.name": "backend", "persistant-agent.repo": "/repo/backend"}},
        "State": {"Status": "running"},
        "NetworkSettings": {"Ports": {"8080/tcp": [{"HostPort": "57779"}]}},
    }

    agent = docker_registry.agent_record(container)

    assert agent.name == "backend"
    assert agent.repo_path == "/repo/backend"
    assert agent.api_url == "http://127.0.0.1:57779"
    assert agent.websocket_url == "ws://127.0.0.1:57779"


def test_list_agents_filters_persistant_agent_containers(monkeypatch):
    monkeypatch.setattr(
        machine_api,
        "list_agent_records",
        lambda: [
            docker_registry.AgentRecord(
                name="a",
                container="persistant-agent-a",
                status="running",
                repo_path=None,
                port=50001,
                api_url="http://127.0.0.1:50001",
                websocket_url="ws://127.0.0.1:50001",
            )
        ],
    )

    response = TestClient(machine_api.app).get("/agents")

    assert response.status_code == 200
    assert response.json()["agents"][0]["name"] == "a"


def test_machine_root_serves_web_ui():
    response = TestClient(machine_api.app).get("/")

    assert response.status_code == 200
    assert "Persistant Agents" in response.text
    assert "/agents" in response.text


def test_start_agent_invokes_compose_and_waits(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(machine_api, "_run", lambda command, env=None: calls.append((command, env)) or type("R", (), {"stdout": ""})())
    monkeypatch.setattr(
        machine_api,
        "_wait_for_agent",
        lambda name: machine_api.AgentRecord(name=name, container="persistant-agent-x", status="running", repo_path=None, port=None, api_url=None, websocket_url=None),
    )

    response = TestClient(machine_api.app).post("/agents/x/start", json={"repo_path": str(tmp_path)})

    assert response.status_code == 200
    assert calls[0][0] == ["docker", "compose", "-p", "persistant-agent-x", "up", "-d", "--build"]
    assert calls[0][1]["REPOSITORY_PATH"] == str(tmp_path.resolve())
    assert calls[0][1]["AGENT_NAME"] == "x"


def test_write_repo_file_rejects_bad_paths_and_base64(tmp_path):
    agent = machine_api.AgentRecord(name="a", container="persistant-agent-a", status="running", repo_path=str(tmp_path), port=None, api_url=None, websocket_url=None)

    for payload in [
        machine_api.FilePayload(path="/tmp/x", content_base64="eA=="),
        machine_api.FilePayload(path="../x", content_base64="eA=="),
        machine_api.FilePayload(path="x", content_base64="not-base64"),
    ]:
        try:
            machine_api.write_repo_file(agent, payload.path, payload.content_base64)
        except HTTPException as exc:
            assert exc.status_code == 400
        else:
            raise AssertionError("expected bad file rejection")


def test_send_files_writes_to_repo_and_optionally_messages(monkeypatch, tmp_path):
    agent = machine_api.AgentRecord(
        name="a",
        container="persistant-agent-a",
        status="running",
        repo_path=str(tmp_path),
        port=None,
        api_url=None,
        websocket_url="ws://agent",
    )
    monkeypatch.setattr(machine_api, "_get_agent_or_404", lambda name: agent)
    monkeypatch.setattr(machine_api, "send_turn", lambda agent, message, thread_id=None: {"thread_id": "t1", "text": message})

    response = TestClient(machine_api.app).post(
        "/agents/a/files",
        json={
            "files": [{"path": "dir/x.txt", "content_base64": base64.b64encode(b"x").decode()}],
            "message": "inspect",
        },
    )

    assert response.status_code == 200
    assert (tmp_path / "dir/x.txt").read_bytes() == b"x"
    assert response.json()["files"][0]["path"] == "dir/x.txt"
    assert response.json()["message"]["text"].startswith("inspect")


def test_send_message_uses_codex_app_server_json_rpc(monkeypatch):
    sent = []

    class FakeWebSocket:
        def __init__(self):
            self.responses = [
                {"id": 1, "result": {}},
                {"id": 2, "result": {"thread": {"id": "thread-1"}}},
                {"id": 3, "result": {"turn": {"id": "turn-1"}}},
                {"method": "item/agentMessage/delta", "params": {"delta": "he"}},
                {"method": "item/agentMessage/delta", "params": {"delta": "llo"}},
                {"method": "turn/completed", "params": {"threadId": "thread-1", "turn": {"id": "turn-1"}}},
            ]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def recv(self):
            return json.dumps(self.responses.pop(0))

        def send(self, payload):
            sent.append(json.loads(payload))

    monkeypatch.setattr(codex_rpc, "agent_ws_token", lambda container: "token")
    monkeypatch.setattr(codex_rpc.websockets.sync.client, "connect", lambda *args, **kwargs: FakeWebSocket())

    response = codex_rpc.send_turn(
        docker_registry.AgentRecord(
            name="a",
            container="persistant-agent-a",
            status="running",
            repo_path=None,
            port=None,
            api_url=None,
            websocket_url="ws://agent",
        ),
        "hello",
    )

    assert response["thread_id"] == "thread-1"
    assert response["text"] == "hello"
    assert [item["method"] for item in sent] == ["initialize", "initialized", "thread/start", "turn/start"]
    assert sent[2]["params"]["sandbox"] == "danger-full-access"
    assert sent[3]["params"]["input"] == [{"type": "text", "text": "hello"}]
