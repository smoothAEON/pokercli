from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from dotenv import dotenv_values, set_key, unset_key

from pokercli.llm import ProviderProfile

DEFAULT_SEATS = 6
DEFAULT_HUMAN_SEAT = 1
DEFAULT_STACK_BB = 100
DEFAULT_MAX_HANDS = 50
DEFAULT_TIMEOUT_S = 30.0
DEFAULT_TEMPERATURE = 0.0
SUPPORTED_PROVIDERS = ("openai", "anthropic", "openrouter", "nvidia", "openai-compatible")


@dataclass(slots=True)
class LiveSeatConfig:
    seat_number: int
    name: str
    provider: str
    model: str
    api_key: str
    base_url: str | None = None
    timeout_s: float = DEFAULT_TIMEOUT_S
    temperature: float = DEFAULT_TEMPERATURE

    def to_profile(self) -> ProviderProfile:
        return ProviderProfile(
            name=f"seat-{self.seat_number}-{self.name.lower().replace(' ', '-')}",
            provider=self.provider,
            model=self.model,
            api_key_env=seat_key(self.seat_number, "API_KEY"),
            base_url=self.base_url,
            timeout_s=self.timeout_s,
            temperature=self.temperature,
        )


def env_path() -> Path:
    override = os.getenv("POKER_ENV_PATH")
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parent.parent / ".env"


def load_env_values(path: Path | None = None) -> dict[str, str]:
    target = path or env_path()
    if not target.exists():
        return {}
    return {key: str(value) for key, value in dotenv_values(target).items() if value is not None}


def write_env_values(
    updates: dict[str, str],
    *,
    remove_keys: Iterable[str] | None = None,
    path: Path | None = None,
) -> None:
    target = path or env_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.touch(exist_ok=True)
    for key in remove_keys or ():
        unset_key(str(target), key, quote_mode="auto")
    for key, value in updates.items():
        set_key(str(target), key, str(value), quote_mode="auto")


def seat_key(seat_number: int, suffix: str) -> str:
    return f"POKER_SEAT_{seat_number}_{suffix}"


def table_defaults(values: dict[str, str]) -> dict[str, int | None]:
    return {
        "seats": _int_value(values.get("POKER_SEATS")),
        "human_seat": _int_value(values.get("POKER_HUMAN_SEAT")),
        "stack_bb": _int_value(values.get("POKER_STACK_BB")),
        "max_hands": _int_value(values.get("POKER_MAX_HANDS")),
    }


def default_model_for_provider(provider: str) -> str:
    normalized = provider.lower()
    if normalized == "anthropic":
        return "claude-sonnet-4-5"
    if normalized == "openrouter":
        return "openai/gpt-4o"
    if normalized == "nvidia":
        return "nvidia/llama-3.1-nemotron-nano-8b-v1"
    return "gpt-5.4-mini"


def default_base_url_for_provider(provider: str) -> str | None:
    normalized = provider.lower()
    if normalized == "openrouter":
        return "https://openrouter.ai/api/v1"
    if normalized == "nvidia":
        return "https://integrate.api.nvidia.com/v1"
    return None


def inspect_seat(values: dict[str, str], seat_number: int) -> tuple[LiveSeatConfig | None, list[str]]:
    relevant_keys = {
        suffix: values.get(seat_key(seat_number, suffix))
        for suffix in ("TYPE", "NAME", "PROVIDER", "MODEL", "API_KEY", "BASE_URL", "TIMEOUT_S", "TEMPERATURE")
    }
    provider = (relevant_keys["PROVIDER"] or "").strip().lower()
    model = (relevant_keys["MODEL"] or "").strip()
    required = ["TYPE", "PROVIDER", "MODEL", "API_KEY", "TIMEOUT_S", "TEMPERATURE"]
    if provider == "openai-compatible":
        required.append("BASE_URL")
    missing = [field for field in required if not (relevant_keys[field] or "").strip()]
    if provider and provider not in SUPPORTED_PROVIDERS:
        missing.append("PROVIDER")
    if missing:
        return None, sorted(set(missing))
    if (relevant_keys["TYPE"] or "").strip().lower() != "llm":
        return None, ["TYPE"]
    try:
        timeout_s = float(relevant_keys["TIMEOUT_S"] or DEFAULT_TIMEOUT_S)
        temperature = float(relevant_keys["TEMPERATURE"] or DEFAULT_TEMPERATURE)
    except ValueError:
        return None, ["TIMEOUT_S", "TEMPERATURE"]
    base_url = (relevant_keys["BASE_URL"] or "").strip() or default_base_url_for_provider(provider)
    return (
        LiveSeatConfig(
            seat_number=seat_number,
            name=model,
            provider=provider,
            model=model,
            api_key=(relevant_keys["API_KEY"] or "").strip(),
            base_url=base_url,
            timeout_s=timeout_s,
            temperature=temperature,
        ),
        [],
    )


def seat_updates(seat_config: LiveSeatConfig) -> dict[str, str]:
    updates = {
        seat_key(seat_config.seat_number, "TYPE"): "llm",
        seat_key(seat_config.seat_number, "NAME"): seat_config.name,
        seat_key(seat_config.seat_number, "PROVIDER"): seat_config.provider,
        seat_key(seat_config.seat_number, "MODEL"): seat_config.model,
        seat_key(seat_config.seat_number, "API_KEY"): seat_config.api_key,
        seat_key(seat_config.seat_number, "TIMEOUT_S"): str(seat_config.timeout_s),
        seat_key(seat_config.seat_number, "TEMPERATURE"): str(seat_config.temperature),
    }
    if seat_config.base_url:
        updates[seat_key(seat_config.seat_number, "BASE_URL")] = seat_config.base_url
    return updates


def table_updates(seats: int, human_seat: int, stack_bb: int, max_hands: int) -> dict[str, str]:
    return {
        "POKER_SEATS": str(seats),
        "POKER_HUMAN_SEAT": str(human_seat),
        "POKER_STACK_BB": str(stack_bb),
        "POKER_MAX_HANDS": str(max_hands),
    }


def seat_remove_keys(seat_number: int, provider: str) -> list[str]:
    remove_keys = [seat_key(seat_number, "IDENTITY")]
    if provider.lower() in {"openai-compatible", "openrouter"}:
        return remove_keys
    return [*remove_keys, seat_key(seat_number, "BASE_URL")]


def _int_value(raw: str | None) -> int | None:
    if raw is None or not raw.strip():
        return None
    try:
        return int(raw)
    except ValueError:
        return None
