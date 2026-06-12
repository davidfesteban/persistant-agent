import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / ".machine"
PID_PATH = STATE_DIR / "machine.pid"
LOG_PATH = STATE_DIR / "machine.log"
HOST = os.environ.get("PERSISTANT_MACHINE_HOST", "127.0.0.1")
PORT = os.environ.get("PERSISTANT_MACHINE_PORT", "8765")
URL = os.environ.get("PERSISTANT_MACHINE_URL", f"http://{HOST}:{PORT}")


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"start", "stop"}:
        print("Usage: machine_daemon.py start|stop", file=sys.stderr)
        return 2
    if sys.argv[1] == "start":
        return start()
    return stop()


def start() -> int:
    STATE_DIR.mkdir(exist_ok=True)
    if healthy():
        print(f"Machine API already running: {URL}")
        return 0
    with LOG_PATH.open("ab") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "persistant_agent.machine_api:app",
                "--host",
                HOST,
                "--port",
                PORT,
            ],
            cwd=ROOT,
            env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    PID_PATH.write_text(str(process.pid))
    for _ in range(30):
        if healthy():
            print(f"Machine API started: {URL}")
            return 0
        time.sleep(1)
    print(LOG_PATH.read_text()[-4000:], file=sys.stderr)
    print("Machine API did not become healthy", file=sys.stderr)
    return 1


def stop() -> int:
    if not PID_PATH.exists():
        print("No machine API pid file")
        return 0
    pid = int(PID_PATH.read_text())
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    PID_PATH.unlink(missing_ok=True)
    print("Machine API stopped")
    return 0


def healthy() -> bool:
    try:
        with urllib.request.urlopen(f"{URL}/health", timeout=2) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


if __name__ == "__main__":
    raise SystemExit(main())
