from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TextIO


class SessionLLMDebugLogger:
    def __init__(self, session_id: str, mode: str, config: dict[str, Any], log_dir: str | Path) -> None:
        self.session_id = session_id
        self.mode = mode
        self.config = config
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.log_dir / f"{session_id}.json"
        self.spool_path = self.log_dir / f"{session_id}.jsonl.tmp"
        self._spool: TextIO | None = self.spool_path.open("a", encoding="utf-8")
        self._finalized = False

    def record_call(self, payload: dict[str, Any]) -> None:
        if self._spool is None:
            return
        self._spool.write(json.dumps(payload))
        self._spool.write("\n")
        self._spool.flush()

    def finalize(self) -> Path:
        if self._finalized:
            return self.path
        self._finalized = True
        if self._spool is not None:
            self._spool.close()
            self._spool = None
        calls: list[dict[str, Any]] = []
        if self.spool_path.exists():
            with self.spool_path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    payload = line.strip()
                    if not payload:
                        continue
                    calls.append(json.loads(payload))
        self.path.write_text(
            json.dumps(
                {
                    "session_id": self.session_id,
                    "mode": self.mode,
                    "debug_level": "DEBUG",
                    "config": self.config,
                    "calls": calls,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        if self.spool_path.exists():
            self.spool_path.unlink()
        return self.path
