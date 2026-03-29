from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.storage import Storage


@dataclass
class CvRunState:
    session_id: str
    process: subprocess.Popen[str]
    log_path: Path


class ComputerVisionManager:
    def __init__(self, storage: Storage, script_path: str, logs_dir: str) -> None:
        self.storage = storage
        self.script_path = Path(script_path)
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._current: CvRunState | None = None

    def start_session(self, session: dict[str, Any]) -> dict[str, Any]:
        session_id = session["session_id"]
        with self._lock:
            self._stop_locked(timeout_seconds=8.0)
            if not self.script_path.exists():
                return {
                    "started": False,
                    "session_id": session_id,
                    "error": f"Computer vision script not found at {self.script_path}",
                }

            log_path = self.logs_dir / f"{session_id}.log"
            ready_path = self.logs_dir / f"{session_id}-{uuid.uuid4().hex}.ready"
            log_handle = log_path.open("a", encoding="utf-8")
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            env["STUDYCLAW_SESSION_ID"] = session_id
            env["STUDYCLAW_CV_READY_FILE"] = str(ready_path)

            creationflags = 0
            if os.name == "nt":
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

            process = subprocess.Popen(
                [sys.executable, str(self.script_path)],
                cwd=str(self.script_path.parent.parent),
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
                creationflags=creationflags,
            )
            self._current = CvRunState(session_id=session_id, process=process, log_path=log_path)

            startup_deadline = time.time() + 45.0
            while time.time() < startup_deadline:
                if process.poll() is not None:
                    log_handle.flush()
                    log_handle.close()
                    self._current = None
                    return {
                        "started": False,
                        "session_id": session_id,
                        "returncode": process.returncode,
                        "log_path": str(log_path),
                        "error": self._read_log_tail(log_path) or "Computer vision process exited during startup.",
                    }
                if ready_path.exists():
                    break
                time.sleep(0.05)
            else:
                self._stop_locked(timeout_seconds=5.0)
                log_handle.close()
                ready_path.unlink(missing_ok=True)
                return {
                    "started": False,
                    "session_id": session_id,
                    "log_path": str(log_path),
                    "error": "Computer vision did not become ready before the startup timeout expired.",
                }

            ready_path.unlink(missing_ok=True)

            threading.Thread(
                target=self._monitor_process,
                args=(session_id, process, log_handle),
                daemon=True,
            ).start()

        return {
            "started": True,
            "session_id": session_id,
            "pid": process.pid,
            "log_path": str(log_path),
        }

    def stop_session(self, session_id: str, timeout_seconds: float = 8.0) -> dict[str, Any]:
        with self._lock:
            if not self._current or self._current.session_id != session_id:
                return {"stopped": False, "session_id": session_id, "reason": "not-running"}
            return self._stop_locked(timeout_seconds=timeout_seconds)

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            if not self._current:
                return {"running": False, "session_id": None}
            running = self._current.process.poll() is None
            return {
                "running": running,
                "session_id": self._current.session_id,
                "pid": self._current.process.pid,
                "log_path": str(self._current.log_path),
            }

    def _stop_locked(self, timeout_seconds: float) -> dict[str, Any]:
        if not self._current:
            return {"stopped": False, "reason": "not-running"}

        current = self._current
        process = current.process
        if process.poll() is None:
            try:
                if os.name == "nt":
                    process.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    process.send_signal(signal.SIGINT)
                process.wait(timeout=timeout_seconds)
            except Exception:
                process.kill()
                process.wait(timeout=timeout_seconds)

        self._current = None
        return {
            "stopped": True,
            "session_id": current.session_id,
            "returncode": process.returncode,
            "log_path": str(current.log_path),
        }

    def _read_log_tail(self, log_path: Path, max_chars: int = 1200) -> str:
        try:
            text = log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        text = text.strip()
        if len(text) <= max_chars:
            return text
        return text[-max_chars:]

    def _monitor_process(
        self,
        session_id: str,
        process: subprocess.Popen[str],
        log_handle,
    ) -> None:
        try:
            process.wait()
        finally:
            log_handle.close()

        with self._lock:
            if not self._current or self._current.process is not process:
                return
            self._current = None

        active_session = self.storage.get_active_session()
        if active_session and active_session.get("session_id") == session_id:
            self.storage.stop_session(session_id, _utc_now_iso())


def _utc_now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
