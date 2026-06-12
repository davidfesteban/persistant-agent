from dataclasses import dataclass
from pathlib import Path
import threading
import time

import pexpect


@dataclass(frozen=True)
class CodexState:
    running: bool
    target_repo: str
    command: list[str]
    pid: int | None


class CodexSession:
    def __init__(self, argv: list[str], target_repo: Path):
        self._argv = argv
        self._target_repo = target_repo
        self._lock = threading.RLock()
        self._child: pexpect.spawn | None = None

    def start(self) -> None:
        with self._lock:
            if self._is_running_locked():
                return
            self._target_repo.mkdir(parents=True, exist_ok=True)
            self._child = pexpect.spawn(
                self._argv[0],
                self._argv[1:],
                cwd=str(self._target_repo),
                encoding="utf-8",
                echo=False,
                timeout=1,
            )
            time.sleep(0.2)

    def state(self) -> CodexState:
        with self._lock:
            return CodexState(
                running=self._is_running_locked(),
                target_repo=str(self._target_repo),
                command=self._argv,
                pid=self._child.pid if self._child is not None else None,
            )

    def send_lines(self, lines: list[str]) -> list[str]:
        with self._lock:
            self.start()
            if self._child is None:
                raise RuntimeError("Codex session did not start")
            for line in lines:
                self._child.sendline(line)
            return lines

    def _is_running_locked(self) -> bool:
        return self._child is not None and self._child.isalive()
