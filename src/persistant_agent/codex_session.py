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


@dataclass(frozen=True)
class OutputEvent:
    seq: int
    type: str
    data: str


class CodexSession:
    def __init__(self, argv: list[str], target_repo: Path):
        self._argv = argv
        self._target_repo = target_repo
        self._lock = threading.RLock()
        self._output_ready = threading.Condition(self._lock)
        self._child: pexpect.spawn | None = None
        self._reader: threading.Thread | None = None
        self._output: list[OutputEvent] = []
        self._next_seq = 1

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
            self._reader = threading.Thread(target=self._read_output, daemon=True)
            self._reader.start()
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

    def output_events_since(self, seq: int) -> list[OutputEvent]:
        with self._lock:
            return [event for event in self._output if event.seq > seq]

    def wait_for_output(self, seq: int, timeout: float) -> list[OutputEvent]:
        with self._output_ready:
            if not any(event.seq > seq for event in self._output):
                self._output_ready.wait(timeout)
            return [event for event in self._output if event.seq > seq]

    def _is_running_locked(self) -> bool:
        return self._child is not None and self._child.isalive()

    def _read_output(self) -> None:
        while True:
            with self._lock:
                child = self._child
                if child is None:
                    return
            try:
                chunk = child.read_nonblocking(size=4096, timeout=0.1)
            except pexpect.TIMEOUT:
                continue
            except pexpect.EOF:
                with self._lock:
                    self._append_output_locked("exit", "")
                return
            if chunk:
                with self._lock:
                    self._append_output_locked("output", chunk)

    def _append_output_locked(self, event_type: str, data: str) -> None:
        self._output.append(OutputEvent(seq=self._next_seq, type=event_type, data=data))
        self._next_seq += 1
        self._output_ready.notify_all()
