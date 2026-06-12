from fastapi.testclient import TestClient
import yaml

from persistant_agent.api import app, session


class FakeSession:
    def __init__(self):
        self.lines = []
        self.events = []

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
        self.events.append(type("Event", (), {"seq": len(self.events) + 1, "type": "output", "data": "streamed"})())
        return lines

    def output_events_since(self, seq):
        return [event for event in self.events if event.seq > seq]

    def wait_for_output(self, seq, timeout):
        return self.output_events_since(seq)


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
    assert response.json()["websocket_url"] == "/ws"
    assert response.json()["commands"]["send_message"] == "POST /messages"
    assert response.json()["websocket_commands"]["message"] == '{"type":"message","message":"text"}'


def test_websocket_sends_commands_and_streams_output(monkeypatch):
    fake = FakeSession()
    monkeypatch.setattr("persistant_agent.api.session", fake)

    with TestClient(app).websocket_connect("/ws") as websocket:
        assert websocket.receive_json()["type"] == "ready"

        websocket.send_json({"type": "message", "message": "hello"})

        assert websocket.receive_json() == {"type": "ack", "sent": ["hello"]}
        assert websocket.receive_json() == {"type": "output", "seq": 1, "data": "streamed"}
