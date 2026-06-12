import importlib

from fastapi.testclient import TestClient

from machine import docker

machine_app = importlib.import_module("machine.app")


def test_agent_from_container():
    agent = docker.agent_from_container(
        {
            "Name": "/persistant-agent-api",
            "Config": {
                "Labels": {"persistant-agent.name": "api", "persistant-agent.repo": "/repo"},
            },
            "State": {"Status": "running"},
            "NetworkSettings": {"Ports": {"8080/tcp": [{"HostPort": "50123"}]}},
        }
    )

    assert agent.name == "api"
    assert agent.api_url == "http://127.0.0.1:50123"
    assert agent.websocket_url == "ws://127.0.0.1:50123"


def test_routes_list_agents(monkeypatch):
    monkeypatch.setattr(
        docker,
        "list_agents",
        lambda: [docker.Agent(name="api", container="persistant-agent-api", status="running", port=50123)],
    )

    response = TestClient(machine_app.app).get("/agents")

    assert response.status_code == 200
    assert response.json()["agents"][0]["name"] == "api"


def test_root_serves_static_web_ui():
    response = TestClient(machine_app.app).get("/")

    assert response.status_code == 200
    assert "new WebSocket(current.websocket_url)" in response.text
    assert "thread/start" in response.text


def test_start_agent_invokes_compose(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(docker, "run", lambda command, env=None: calls.append((command, env)) or type("R", (), {"stdout": ""})())
    monkeypatch.setattr(machine_app, "_wait", lambda name: docker.Agent(name=name, container="persistant-agent-api", status="running"))

    response = TestClient(machine_app.app).post("/agents/api/start", json={"repo_path": str(tmp_path)})

    assert response.status_code == 200
    assert calls[0][0] == ["docker", "compose", "-p", "persistant-agent-api", "up", "-d", "--build"]
    assert calls[0][1]["AGENT_NAME"] == "api"
    assert calls[0][1]["REPOSITORY_PATH"] == str(tmp_path.resolve())
    assert set(calls[0][1]) >= {"AGENT_NAME", "REPOSITORY_PATH"}


def test_routes_do_not_proxy_messages():
    paths = TestClient(machine_app.app).get("/openapi.json").json()["paths"]

    assert "/agents/{name}/messages" not in paths
    assert "/agents/{name}/files" not in paths
