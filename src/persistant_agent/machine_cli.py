import json
import os
import sys
import urllib.error
import urllib.request


MACHINE_URL = os.environ.get("PERSISTANT_MACHINE_URL", "http://127.0.0.1:8765").rstrip("/")
MACHINE_TOKEN = os.environ.get("PERSISTANT_MACHINE_TOKEN", "")


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: machine_cli.py start <repo> <name> | stop <name> | agents", file=sys.stderr)
        return 2
    command = sys.argv[1]
    if command == "start" and len(sys.argv) == 4:
        payload = {"repo_path": sys.argv[2]}
        response = request("POST", f"/agents/{sys.argv[3]}/start", payload)
        print_agent(response)
        return 0
    if command == "stop" and len(sys.argv) == 3:
        response = request("POST", f"/agents/{sys.argv[2]}/stop", None)
        print(json.dumps(response))
        return 0
    if command == "agents" and len(sys.argv) == 2:
        print(json.dumps(request("GET", "/agents", None), indent=2))
        return 0
    print("Invalid command", file=sys.stderr)
    return 2


def request(method: str, path: str, payload: dict | None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{MACHINE_URL}{path}", data=data, method=method)
    req.add_header("content-type", "application/json")
    if MACHINE_TOKEN:
        req.add_header("authorization", f"Bearer {MACHINE_TOKEN}")
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()
        print(detail or str(exc), file=sys.stderr)
        raise SystemExit(1) from exc


def print_agent(agent: dict) -> None:
    print(f"Agent {agent['name']} {agent['status']}")
    if agent.get("api_url"):
        print(f"API: {agent['api_url']}")
    if agent.get("websocket_url"):
        print(f"WebSocket: {agent['websocket_url']}")


if __name__ == "__main__":
    raise SystemExit(main())
