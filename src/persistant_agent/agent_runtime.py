import json
import os
from pathlib import Path


AGENT_CWD = "/workspace/repo"
PROJECT_ROOT = Path(os.environ.get("PERSISTANT_AGENT_HOME", Path(__file__).resolve().parents[2]))
WS_TOKEN_ENV = "PERSISTANT_AGENT_WS_TOKEN"
DEFAULT_WS_TOKEN = "persistant-agent-local-token"
APP_SERVER_COMMAND = [
    "/bin/sh",
    "-lc",
    (
        "printf '%s' \"$CODEX_WS_TOKEN\" > /tmp/codex-ws-token "
        "&& chmod 600 /tmp/codex-ws-token "
        "&& exec codex app-server "
        "--listen ws://0.0.0.0:8080 "
        "--ws-auth capability-token "
        "--ws-token-file /tmp/codex-ws-token "
        "-c sandbox_mode=\\\"danger-full-access\\\" "
        "-c approval_policy=\\\"never\\\""
    ),
]


def app_server_command_json() -> str:
    return json.dumps(APP_SERVER_COMMAND)
