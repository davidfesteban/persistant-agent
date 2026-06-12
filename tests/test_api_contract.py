from fastapi.testclient import TestClient
import yaml

from persistant_agent.api import app, session


class FakeSession:
    def __init__(self):
        self.lines = []

    def start(self):
        return None

    def state(self):
        return type(
            "State",
            (),
            {
                "running": True,
                "target_repo": "/tmp/repo",
                "command": ["codex"],
                "pid": 123,
                "__dict__": {
                    "running": True,
                    "target_repo": "/tmp/repo",
                    "command": ["codex"],
                    "pid": 123,
                },
            },
        )()

    def send_lines(self, lines):
        self.lines.extend(lines)
        return lines


def test_message_endpoint_sends_text(monkeypatch):
    fake = FakeSession()
    monkeypatch.setattr("persistant_agent.api.session", fake)

    response = TestClient(app).post("/messages", json={"message": "implement the OpenAPI change"})

    assert response.status_code == 202
    assert response.json() == {"accepted": True, "sent": ["implement the OpenAPI change"]}
    assert fake.lines == ["implement the OpenAPI change"]


def test_context_endpoint_maps_empty_and_compact(monkeypatch):
    fake = FakeSession()
    monkeypatch.setattr("persistant_agent.api.session", fake)
    client = TestClient(app)

    assert client.post("/context", json={"action": "empty"}).json()["sent"] == ["/clear"]
    assert client.post("/context", json={"action": "compact"}).json()["sent"] == ["/compact"]


def test_model_endpoint_sends_model_and_effort(monkeypatch):
    fake = FakeSession()
    monkeypatch.setattr("persistant_agent.api.session", fake)

    response = TestClient(app).post("/session/model", json={"model": "gpt-5.4", "effort": "high"})

    assert response.status_code == 202
    assert response.json()["sent"] == ["/model gpt-5.4", "/reasoning high"]


def test_openapi_json_serves_checked_in_contract():
    expected = yaml.safe_load(open("openapi.yaml").read())

    response = TestClient(app).get("/openapi.json")

    assert response.status_code == 200
    assert response.json() == expected


def test_root_serves_machine_readable_discovery():
    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert response.json()["openapi_url"] == "/openapi.json"
    assert response.json()["docs_url"] == "/docs"
    assert response.json()["commands"]["send_message"] == "POST /messages"
