from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_config_dir, user_data_dir

APP_NAME = "pokercli"


@dataclass(slots=True)
class AppConfig:
    database_path: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {"database_path": self.database_path}

    @classmethod
    def from_dict(cls, payload: dict[str, str | None]) -> "AppConfig":
        return cls(database_path=payload.get("database_path"))


def config_dir() -> Path:
    return Path(user_config_dir(APP_NAME))


def data_dir() -> Path:
    return Path(user_data_dir(APP_NAME))


def config_path() -> Path:
    return config_dir() / "config.json"


def default_database_path() -> Path:
    return data_dir() / "poker.sqlite3"


def default_llm_debug_dir() -> Path:
    return Path.cwd() / "llm_debug"


def load_config() -> AppConfig:
    path = config_path()
    if not path.exists():
        return AppConfig(database_path=str(default_database_path()))
    return AppConfig.from_dict(json.loads(path.read_text(encoding="utf-8")))


def save_config(config: AppConfig) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not config.database_path:
        config.database_path = str(default_database_path())
    path.write_text(json.dumps(config.to_dict(), indent=2), encoding="utf-8")
