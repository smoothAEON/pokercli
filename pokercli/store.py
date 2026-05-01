from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from pokercli.engine import HandHistory


class PokerStorage:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        self.connection.close()

    def _init_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                mode TEXT NOT NULL,
                started_at TEXT DEFAULT CURRENT_TIMESTAMP,
                config_json TEXT NOT NULL,
                seed INTEGER,
                summary_json TEXT
            );

            CREATE TABLE IF NOT EXISTS hands (
                hand_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                hand_no INTEGER NOT NULL,
                hand_json TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES sessions(session_id)
            );

            CREATE TABLE IF NOT EXISTS actions (
                hand_id TEXT NOT NULL,
                action_index INTEGER NOT NULL,
                action_json TEXT NOT NULL,
                PRIMARY KEY(hand_id, action_index),
                FOREIGN KEY(hand_id) REFERENCES hands(hand_id)
            );

            CREATE TABLE IF NOT EXISTS llm_turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                hand_no INTEGER NOT NULL,
                seat INTEGER NOT NULL,
                provider TEXT,
                model TEXT,
                success INTEGER NOT NULL,
                request_json TEXT NOT NULL,
                response_json TEXT,
                error_text TEXT
            );

            CREATE TABLE IF NOT EXISTS simulation_runs (
                session_id TEXT PRIMARY KEY,
                summary_json TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES sessions(session_id)
            );
            """
        )
        self.connection.commit()

    def record_session(self, session_id: str, mode: str, config: dict[str, Any], seed: int | None) -> None:
        self.connection.execute(
            """
            INSERT OR REPLACE INTO sessions(session_id, mode, config_json, seed)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, mode, json.dumps(config), seed),
        )
        self.connection.commit()

    def record_hand(self, history: HandHistory) -> None:
        hand_id = f"{history.session_id}:{history.hand_no}"
        hand_json = json.dumps(history.to_dict())
        self.connection.execute(
            """
            INSERT OR REPLACE INTO hands(hand_id, session_id, hand_no, hand_json)
            VALUES (?, ?, ?, ?)
            """,
            (hand_id, history.session_id, history.hand_no, hand_json),
        )
        self.connection.executemany(
            """
            INSERT OR REPLACE INTO actions(hand_id, action_index, action_json)
            VALUES (?, ?, ?)
            """,
            [(hand_id, action.index, json.dumps(action.to_dict())) for action in history.actions],
        )
        self.connection.commit()

    def record_llm_turn(
        self,
        session_id: str,
        hand_no: int,
        seat: int,
        provider: str | None,
        model: str | None,
        success: bool,
        request_payload: dict[str, Any],
        response_payload: dict[str, Any] | None,
        error_text: str | None,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO llm_turns(session_id, hand_no, seat, provider, model, success, request_json, response_json, error_text)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                hand_no,
                seat,
                provider,
                model,
                int(success),
                json.dumps(request_payload),
                json.dumps(response_payload) if response_payload is not None else None,
                error_text,
            ),
        )
        self.connection.commit()

    def record_summary(self, session_id: str, summary: dict[str, Any]) -> None:
        summary_json = json.dumps(summary)
        self.connection.execute(
            "UPDATE sessions SET summary_json = ? WHERE session_id = ?",
            (summary_json, session_id),
        )
        self.connection.execute(
            """
            INSERT OR REPLACE INTO simulation_runs(session_id, summary_json)
            VALUES (?, ?)
            """,
            (session_id, summary_json),
        )
        self.connection.commit()

    def load_hand(self, session_id: str | None = None, hand_id: str | None = None) -> dict[str, Any]:
        if hand_id is not None:
            row = self.connection.execute(
                "SELECT hand_json FROM hands WHERE hand_id = ?",
                (hand_id,),
            ).fetchone()
        elif session_id is not None:
            row = self.connection.execute(
                "SELECT hand_json FROM hands WHERE session_id = ? ORDER BY hand_no DESC LIMIT 1",
                (session_id,),
            ).fetchone()
        else:
            raise ValueError("session_id or hand_id is required")
        if row is None:
            raise KeyError("Hand not found")
        return json.loads(row["hand_json"])

    def load_session_hands(self, session_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT hand_json FROM hands WHERE session_id = ? ORDER BY hand_no",
            (session_id,),
        ).fetchall()
        return [json.loads(row["hand_json"]) for row in rows]
