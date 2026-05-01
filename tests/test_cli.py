from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from dotenv import dotenv_values
from typer.testing import CliRunner

from pokercli.agents import HumanController, LLMController, RuleBotController
from pokercli.cli import app
from pokercli.config import AppConfig
from pokercli.live_env import LiveSeatConfig, seat_updates, table_updates, write_env_values
from pokercli.llm import LLMTurnResponse, ProviderProfile, ProviderRequestDebug, ProviderResponseDebug

runner = CliRunner()


class DummyPrompt:
    def __init__(self, value):
        self.value = value

    def ask(self):
        return self.value


class PromptSequence:
    def __init__(self, values):
        self.values = list(values)

    def __call__(self, *args, **kwargs):
        return DummyPrompt(self.values.pop(0))


class DummyProvider:
    def __init__(self, profile: ProviderProfile) -> None:
        self.profile = profile


class FailingProvider:
    def __init__(self, profile: ProviderProfile) -> None:
        self.profile = profile

    def complete_turn(self, request):
        from pokercli.llm.providers import LLMProviderError

        raise LLMProviderError("provider down")


class LoggingProvider:
    def __init__(self, profile: ProviderProfile) -> None:
        self.profile = profile
        self.calls = 0

    def complete_turn(self, request):
        self.calls += 1
        content = '{"action":"check","amount":null,"reason":"fine"}'
        return LLMTurnResponse(
            provider=self.profile.provider,
            model=self.profile.model,
            content=content,
            raw_payload={"choices": [{"message": {"content": content}}]},
            latency_ms=3,
            provider_request=ProviderRequestDebug(
                url="https://example.invalid/v1/chat/completions",
                body={
                    "model": self.profile.model,
                    "messages": [
                        {"role": "system", "content": request.system_prompt},
                        {"role": "user", "content": request.user_prompt},
                    ],
                },
            ),
            provider_response=ProviderResponseDebug(
                status_code=200,
                body={"choices": [{"message": {"content": content}}]},
            ),
        )


def _patch_runtime_paths(monkeypatch, tmp_path: Path) -> tuple[Path, Path]:
    env_file = tmp_path / "custom.env"
    db_file = tmp_path / "poker.sqlite3"
    debug_dir = tmp_path / "llm_debug"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("POKER_ENV_PATH", str(env_file))
    monkeypatch.setattr("pokercli.config.default_database_path", lambda: db_file)
    monkeypatch.setattr("pokercli.config.default_llm_debug_dir", lambda: debug_dir)
    monkeypatch.setattr("pokercli.cli.default_database_path", lambda: db_file)
    monkeypatch.setattr("pokercli.cli.default_llm_debug_dir", lambda: debug_dir)
    monkeypatch.setattr("pokercli.cli.load_config", lambda: AppConfig(database_path=str(db_file)))
    return env_file, db_file


def _patch_repo_root_runtime(monkeypatch, tmp_path: Path) -> tuple[Path, Path]:
    repo_root = tmp_path / "repo"
    workdir = tmp_path / "outside"
    env_file = repo_root / ".env"
    db_file = tmp_path / "poker.sqlite3"
    debug_dir = tmp_path / "llm_debug"
    (repo_root / "pokercli").mkdir(parents=True)
    workdir.mkdir()
    monkeypatch.delenv("POKER_ENV_PATH", raising=False)
    monkeypatch.chdir(workdir)
    monkeypatch.setattr("pokercli.live_env.__file__", str(repo_root / "pokercli" / "live_env.py"))
    monkeypatch.setattr("pokercli.config.default_database_path", lambda: db_file)
    monkeypatch.setattr("pokercli.config.default_llm_debug_dir", lambda: debug_dir)
    monkeypatch.setattr("pokercli.cli.default_database_path", lambda: db_file)
    monkeypatch.setattr("pokercli.cli.default_llm_debug_dir", lambda: debug_dir)
    monkeypatch.setattr("pokercli.cli.load_config", lambda: AppConfig(database_path=str(db_file)))
    return env_file, db_file


def _seat_config(seat_number: int, *, provider: str = "openai") -> LiveSeatConfig:
    return LiveSeatConfig(
        seat_number=seat_number,
        name=f"Bot {seat_number}",
        provider=provider,
        model=(
            "openai/gpt-4o"
            if provider == "openrouter"
            else "nvidia/llama-3.1-nemotron-nano-8b-v1" if provider == "nvidia" else "gpt-5.4-mini"
        ),
        api_key=f"secret-{seat_number}",
        base_url=(
            "https://openrouter.ai/api/v1"
            if provider == "openrouter"
            else "https://integrate.api.nvidia.com/v1" if provider == "nvidia" else None
        ),
        timeout_s=30.0,
        temperature=0.0,
    )


def _write_live_env(path: Path, *, seats: int, human_seat: int, stack_bb: int = 100, max_hands: int = 50, configs: list[LiveSeatConfig]) -> None:
    updates = table_updates(seats, human_seat, stack_bb, max_hands)
    for config in configs:
        updates.update(seat_updates(config))
    write_env_values(updates, path=path)


def _scripted_act(self, view):
    from pokercli.engine import ActionDecision, ActionType

    if isinstance(self, LLMController):
        for action in view.legal_actions:
            if action.action == ActionType.CHECK:
                return ActionDecision(ActionType.CHECK)
        return ActionDecision(ActionType.CALL)
    for action in view.legal_actions:
        if action.action == ActionType.CHECK:
            return ActionDecision(ActionType.CHECK)
    return ActionDecision(ActionType.CALL)


def _patch_scripted_live_controllers(monkeypatch) -> None:
    monkeypatch.setattr("pokercli.agents.controllers.HumanController.act", _scripted_act)
    monkeypatch.setattr("pokercli.agents.controllers.LLMController.act", _scripted_act)


def _read_single_session_report(base_dir: Path) -> tuple[Path, str]:
    reports = list((base_dir / "reports").glob("pokercli-session-*.txt"))
    assert len(reports) == 1
    return reports[0], reports[0].read_text(encoding="utf-8")


def test_setup_command_writes_repo_root_env(monkeypatch, tmp_path: Path) -> None:
    env_file, _ = _patch_repo_root_runtime(monkeypatch, tmp_path)
    monkeypatch.setattr("pokercli.cli.questionary.text", PromptSequence(["2", "100", "50", "Bot 2", "gpt-5.4-mini", "30", "0"]))
    monkeypatch.setattr("pokercli.cli.questionary.select", PromptSequence(["openai"]))
    monkeypatch.setattr("pokercli.cli.questionary.password", PromptSequence(["secret"]))
    result = runner.invoke(app, ["setup"])
    assert result.exit_code == 0
    assert env_file.exists()
    values = dotenv_values(env_file)
    assert values["POKER_SEATS"] == "2"
    assert values["POKER_HUMAN_SEAT"] == "1"
    assert values["POKER_STACK_BB"] == "100"
    assert values["POKER_MAX_HANDS"] == "50"
    assert values["POKER_SEAT_2_TYPE"] == "llm"
    assert values["POKER_SEAT_2_PROVIDER"] == "openai"
    assert values["POKER_SEAT_2_API_KEY"] == "secret"


def test_setup_command_honors_poker_env_path_override(monkeypatch, tmp_path: Path) -> None:
    env_file, _ = _patch_runtime_paths(monkeypatch, tmp_path)
    monkeypatch.setattr("pokercli.cli.questionary.text", PromptSequence(["2", "100", "50", "Bot 2", "gpt-5.4-mini", "30", "0"]))
    monkeypatch.setattr("pokercli.cli.questionary.select", PromptSequence(["openai"]))
    monkeypatch.setattr("pokercli.cli.questionary.password", PromptSequence(["secret"]))
    result = runner.invoke(app, ["setup"])
    assert result.exit_code == 0
    assert env_file.exists()
    values = dotenv_values(env_file)
    assert values["POKER_SEATS"] == "2"
    assert values["POKER_HUMAN_SEAT"] == "1"
    assert values["POKER_STACK_BB"] == "100"
    assert values["POKER_MAX_HANDS"] == "50"
    assert values["POKER_SEAT_2_TYPE"] == "llm"
    assert values["POKER_SEAT_2_PROVIDER"] == "openai"
    assert values["POKER_SEAT_2_API_KEY"] == "secret"


def test_setup_command_accepts_nvidia_provider(monkeypatch, tmp_path: Path) -> None:
    env_file, _ = _patch_runtime_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "pokercli.cli.questionary.text",
        PromptSequence(["2", "100", "50", "Bot 2", "nvidia/llama-3.1-nemotron-nano-8b-v1", "30", "0"]),
    )
    monkeypatch.setattr("pokercli.cli.questionary.select", PromptSequence(["nvidia"]))
    monkeypatch.setattr("pokercli.cli.questionary.password", PromptSequence(["nvidia-secret"]))
    result = runner.invoke(app, ["setup"])
    assert result.exit_code == 0
    values = dotenv_values(env_file)
    assert values["POKER_SEAT_2_PROVIDER"] == "nvidia"
    assert values["POKER_SEAT_2_API_KEY"] == "nvidia-secret"


def test_simulate_and_replay_commands_smoke(monkeypatch, tmp_path: Path) -> None:
    _, db_path = _patch_runtime_paths(monkeypatch, tmp_path)
    result = runner.invoke(app, ["simulate", "--hands", "5", "--seed", "7"])
    assert result.exit_code == 0
    assert "Session Summary" in result.stdout
    with sqlite3.connect(db_path) as connection:
        row = connection.execute("SELECT session_id FROM sessions LIMIT 1").fetchone()
    replay = runner.invoke(app, ["replay", "--session-id", row[0]])
    assert replay.exit_code == 0
    assert "Actions:" in replay.stdout
    assert "result=" in replay.stdout


def test_play_prompts_for_player_count_when_seats_not_provided(monkeypatch, tmp_path: Path) -> None:
    env_file, db_path = _patch_runtime_paths(monkeypatch, tmp_path)
    monkeypatch.setattr("pokercli.cli.questionary.text", PromptSequence(["2", "Bot 2", "gpt-5.4-mini", "30", "0"]))
    monkeypatch.setattr("pokercli.cli.questionary.select", PromptSequence(["openai"]))
    monkeypatch.setattr("pokercli.cli.questionary.password", PromptSequence(["secret"]))
    monkeypatch.setattr("pokercli.cli.questionary.confirm", lambda *args, **kwargs: DummyPrompt(False))
    monkeypatch.setattr("pokercli.cli.provider_from_profile", lambda profile, api_key: DummyProvider(profile))
    _patch_scripted_live_controllers(monkeypatch)
    result = runner.invoke(app, ["play", "--max-hands", "1"])
    assert result.exit_code == 0
    assert "Session Summary" in result.stdout
    assert "LLM Status" in result.stdout
    values = dotenv_values(env_file)
    assert values["POKER_SEATS"] == "2"
    assert values["POKER_HUMAN_SEAT"] == "1"
    assert values["POKER_STACK_BB"] == "100"
    assert values["POKER_MAX_HANDS"] == "1"
    assert values["POKER_SEAT_2_API_KEY"] == "secret"
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1


def test_play_writes_report_when_user_stops(monkeypatch, tmp_path: Path) -> None:
    env_file, _ = _patch_runtime_paths(monkeypatch, tmp_path)
    _write_live_env(env_file, seats=2, human_seat=1, max_hands=2, configs=[_seat_config(2)])
    monkeypatch.setattr("pokercli.cli.questionary.confirm", lambda *args, **kwargs: DummyPrompt(False))
    monkeypatch.setattr("pokercli.cli.provider_from_profile", lambda profile, api_key: DummyProvider(profile))
    _patch_scripted_live_controllers(monkeypatch)

    result = runner.invoke(app, ["play", "--seats", "2", "--max-hands", "2"])

    assert result.exit_code == 0
    assert "Session report saved to" in result.stdout
    assert "reports\\pokercli-session-" in result.stdout
    report_path, report_text = _read_single_session_report(tmp_path)
    assert report_path.name.startswith("pokercli-session-")
    assert "End reason: user-stopped" in report_text
    assert "Hands completed: 1" in report_text
    assert "Hand Details:" in report_text
    assert "result=" in report_text


def test_play_with_explicit_seats_skips_player_count_prompt(monkeypatch, tmp_path: Path) -> None:
    env_file, _ = _patch_runtime_paths(monkeypatch, tmp_path)
    text_prompts = PromptSequence(["Bot 2", "gpt-5.4-mini", "30", "0"])

    def prompt_text(message, *args, **kwargs):
        if message == "How many players?":
            raise AssertionError("unexpected seat-count prompt")
        return text_prompts(message, *args, **kwargs)

    monkeypatch.setattr("pokercli.cli.questionary.text", prompt_text)
    monkeypatch.setattr("pokercli.cli.questionary.select", PromptSequence(["openai"]))
    monkeypatch.setattr("pokercli.cli.questionary.password", PromptSequence(["secret"]))
    monkeypatch.setattr("pokercli.cli.questionary.confirm", lambda *args, **kwargs: DummyPrompt(False))
    monkeypatch.setattr("pokercli.cli.provider_from_profile", lambda profile, api_key: DummyProvider(profile))
    _patch_scripted_live_controllers(monkeypatch)
    result = runner.invoke(app, ["play", "--seats", "2", "--max-hands", "1"])
    assert result.exit_code == 0
    values = dotenv_values(env_file)
    assert values["POKER_SEATS"] == "2"
    assert values["POKER_HUMAN_SEAT"] == "1"
    assert values["POKER_STACK_BB"] == "100"
    assert values["POKER_MAX_HANDS"] == "1"
    assert values["POKER_SEAT_2_API_KEY"] == "secret"


def test_play_partial_env_prompts_only_missing_seat(monkeypatch, tmp_path: Path) -> None:
    env_file, _ = _patch_runtime_paths(monkeypatch, tmp_path)
    _write_live_env(
        env_file,
        seats=3,
        human_seat=1,
        max_hands=1,
        configs=[_seat_config(2)],
    )
    monkeypatch.setattr("pokercli.cli.questionary.text", PromptSequence(["Bot 3", "gpt-5.4-mini", "30", "0"]))
    monkeypatch.setattr("pokercli.cli.questionary.select", PromptSequence(["openai"]))
    monkeypatch.setattr("pokercli.cli.questionary.password", PromptSequence(["secret-3"]))
    monkeypatch.setattr("pokercli.cli.questionary.confirm", lambda *args, **kwargs: DummyPrompt(False))
    monkeypatch.setattr("pokercli.cli.provider_from_profile", lambda profile, api_key: DummyProvider(profile))
    _patch_scripted_live_controllers(monkeypatch)
    result = runner.invoke(app, ["play", "--seats", "3", "--max-hands", "1"])
    assert result.exit_code == 0
    values = dotenv_values(env_file)
    assert values["POKER_SEAT_2_API_KEY"] == "secret-2"
    assert values["POKER_SEAT_3_API_KEY"] == "secret-3"


def test_play_cancelled_onboarding_exits_without_env(monkeypatch, tmp_path: Path) -> None:
    env_file, _ = _patch_runtime_paths(monkeypatch, tmp_path)
    monkeypatch.setattr("pokercli.cli.questionary.text", PromptSequence(["Bot 2", "gpt-5.4-mini", "30", "0"]))
    monkeypatch.setattr("pokercli.cli.questionary.select", PromptSequence(["openai"]))
    monkeypatch.setattr("pokercli.cli.questionary.password", PromptSequence([""]))
    result = runner.invoke(app, ["play", "--seats", "2", "--max-hands", "1"])
    assert result.exit_code == 1
    assert not env_file.exists()


def test_play_cancelled_onboarding_without_existing_env_does_not_write_partial_defaults(
    monkeypatch, tmp_path: Path
) -> None:
    env_file, _ = _patch_runtime_paths(monkeypatch, tmp_path)
    monkeypatch.setattr("pokercli.cli.questionary.text", PromptSequence(["2", "Bot 2", "gpt-5.4-mini", "30", "0"]))
    monkeypatch.setattr("pokercli.cli.questionary.select", PromptSequence(["openai"]))
    monkeypatch.setattr("pokercli.cli.questionary.password", PromptSequence([""]))
    result = runner.invoke(app, ["play", "--max-hands", "1"])
    assert result.exit_code == 1
    assert not env_file.exists()


def test_play_rejects_non_default_human_seat(monkeypatch, tmp_path: Path) -> None:
    _patch_runtime_paths(monkeypatch, tmp_path)
    result = runner.invoke(app, ["play", "--seats", "2", "--human-seat", "2"])
    assert result.exit_code == 2
    assert "human-seat is fixed to 1 for live play." in result.stderr


def test_controllers_from_live_seats_use_human_and_llm_only(monkeypatch) -> None:
    monkeypatch.setattr("pokercli.cli.provider_from_profile", lambda profile, api_key: DummyProvider(profile))
    from pokercli.cli import _controllers_from_live_seats

    seat_configs = {seat_number: _seat_config(seat_number) for seat_number in range(2, 7)}
    for seats in (2, 6):
        names, controllers = _controllers_from_live_seats(seats, 1, seat_configs, status_callback=None)
        assert names[0] == "You"
        assert isinstance(controllers[0], HumanController)
        for seat in range(1, seats):
            assert isinstance(controllers[seat], LLMController)
            assert not isinstance(controllers[seat], RuleBotController)


def test_play_ignores_extra_unused_seat_blocks(monkeypatch, tmp_path: Path) -> None:
    env_file, _ = _patch_runtime_paths(monkeypatch, tmp_path)
    _write_live_env(
        env_file,
        seats=4,
        human_seat=1,
        max_hands=1,
        configs=[_seat_config(2, provider="openrouter"), _seat_config(3), _seat_config(4)],
    )
    monkeypatch.setattr("pokercli.cli.questionary.select", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected onboarding prompt")))
    monkeypatch.setattr("pokercli.cli.questionary.text", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected onboarding prompt")))
    monkeypatch.setattr("pokercli.cli.questionary.password", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected onboarding prompt")))
    monkeypatch.setattr("pokercli.cli.questionary.confirm", lambda *args, **kwargs: DummyPrompt(False))
    monkeypatch.setattr("pokercli.cli.provider_from_profile", lambda profile, api_key: DummyProvider(profile))
    _patch_scripted_live_controllers(monkeypatch)
    result = runner.invoke(app, ["play", "--seats", "2", "--max-hands", "1"])
    assert result.exit_code == 0
    assert "openrouter" in result.stdout


def test_play_normalizes_existing_env_human_seat_to_seat_one(monkeypatch, tmp_path: Path) -> None:
    env_file, _ = _patch_runtime_paths(monkeypatch, tmp_path)
    _write_live_env(env_file, seats=2, human_seat=2, max_hands=1, configs=[_seat_config(2)])
    monkeypatch.setattr("pokercli.cli.questionary.select", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected select prompt")))
    monkeypatch.setattr("pokercli.cli.questionary.text", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected text prompt")))
    monkeypatch.setattr("pokercli.cli.questionary.password", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected password prompt")))
    monkeypatch.setattr("pokercli.cli.questionary.confirm", lambda *args, **kwargs: DummyPrompt(False))
    monkeypatch.setattr("pokercli.cli.provider_from_profile", lambda profile, api_key: DummyProvider(profile))
    _patch_scripted_live_controllers(monkeypatch)
    result = runner.invoke(app, ["play", "--seats", "2", "--max-hands", "1"])
    assert result.exit_code == 0
    assert "Seat 1: You" in result.stdout
    assert "Seat 2: You" not in result.stdout


def test_play_live_llm_failure_shows_status_and_can_end_session(monkeypatch, tmp_path: Path) -> None:
    env_file, _ = _patch_runtime_paths(monkeypatch, tmp_path)
    _write_live_env(env_file, seats=2, human_seat=1, max_hands=1, configs=[_seat_config(2)])
    monkeypatch.setattr("pokercli.cli.provider_from_profile", lambda selected_profile, api_key: FailingProvider(selected_profile))
    monkeypatch.setattr("pokercli.cli.questionary.select", PromptSequence(["End session"]))

    def human_act(self, view):
        from pokercli.engine import ActionDecision, ActionType

        for action in view.legal_actions:
            if action.action == ActionType.CHECK:
                return ActionDecision(ActionType.CHECK)
        return ActionDecision(ActionType.CALL)

    monkeypatch.setattr("pokercli.agents.controllers.HumanController.act", human_act)
    result = runner.invoke(app, ["play", "--seats", "2", "--max-hands", "1"])
    assert result.exit_code == 0
    assert "LLM Status" in result.stdout
    assert "failed" in result.stdout
    assert "Live session ended after an LLM failure." in result.stdout
    _, report_text = _read_single_session_report(tmp_path)
    assert "End reason: llm-failure" in report_text
    assert "No completed hands." in report_text


def test_simulate_llm_lineup_uses_env_seat_and_forces_temperature_zero(monkeypatch, tmp_path: Path) -> None:
    env_file, _ = _patch_runtime_paths(monkeypatch, tmp_path)
    lineup_file = tmp_path / "lineup.json"
    captured_profiles = []
    config = _seat_config(2)
    config.temperature = 0.75
    _write_live_env(env_file, seats=2, human_seat=1, configs=[config])
    lineup_file.write_text(
        json.dumps(
            [
                {"type": "llm", "env_seat": 2, "name": "GPT Seat"},
                {"type": "rule", "name": "Rule Seat"},
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "pokercli.cli.provider_from_profile",
        lambda profile, api_key: captured_profiles.append(profile) or DummyProvider(profile),
    )
    monkeypatch.setattr("pokercli.agents.controllers.LLMController.act", _scripted_act)
    result = runner.invoke(app, ["simulate", "--hands", "1", "--lineup", str(lineup_file)])
    assert result.exit_code == 0
    assert captured_profiles[0].api_key_env == "POKER_SEAT_2_API_KEY"
    assert captured_profiles[0].temperature == 0.0


def test_simulate_llm_lineup_requires_complete_env_seat(monkeypatch, tmp_path: Path) -> None:
    env_file, _ = _patch_runtime_paths(monkeypatch, tmp_path)
    lineup_file = tmp_path / "lineup.json"
    lineup_file.write_text(json.dumps([{"type": "llm", "env_seat": 2}]), encoding="utf-8")
    _write_live_env(env_file, seats=2, human_seat=1, configs=[])
    result = runner.invoke(app, ["simulate", "--hands", "1", "--lineup", str(lineup_file)])
    assert result.exit_code == 2
    assert "env_seat 2" in result.stderr


def test_simulate_llm_lineup_rejects_incomplete_env_seat_fields(monkeypatch, tmp_path: Path) -> None:
    env_file, _ = _patch_runtime_paths(monkeypatch, tmp_path)
    lineup_file = tmp_path / "lineup.json"
    lineup_file.write_text(json.dumps([{"type": "llm", "env_seat": 2}]), encoding="utf-8")
    write_env_values(
        {
            "POKER_SEATS": "2",
            "POKER_HUMAN_SEAT": "1",
            "POKER_SEAT_2_TYPE": "llm",
            "POKER_SEAT_2_NAME": "Bot 2",
            "POKER_SEAT_2_PROVIDER": "openai",
            "POKER_SEAT_2_MODEL": "gpt-5.4-mini",
            "POKER_SEAT_2_TIMEOUT_S": "30",
            "POKER_SEAT_2_TEMPERATURE": "0",
        },
        path=env_file,
    )
    result = runner.invoke(app, ["simulate", "--hands", "1", "--lineup", str(lineup_file)])
    assert result.exit_code == 2
    assert "API_KEY" in result.stderr


def test_simulate_debug_llm_log_writes_single_session_file(monkeypatch, tmp_path: Path) -> None:
    env_file, _ = _patch_runtime_paths(monkeypatch, tmp_path)
    lineup_file = tmp_path / "lineup.json"
    _write_live_env(env_file, seats=2, human_seat=1, configs=[_seat_config(2)])
    lineup_file.write_text(
        json.dumps(
            [
                {"type": "llm", "env_seat": 2, "name": "GPT Seat"},
                {"type": "rule", "name": "Rule Seat"},
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("pokercli.cli.provider_from_profile", lambda profile, api_key: LoggingProvider(profile))
    result = runner.invoke(app, ["simulate", "--hands", "1", "--lineup", str(lineup_file), "--debug-llm-log"])
    assert result.exit_code == 0
    files = sorted((tmp_path / "llm_debug").glob("*.json"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["mode"] == "simulate"
    assert payload["debug_level"] == "DEBUG"
    assert payload["config"]["max_hands"] == 1
    assert payload["calls"]
    first_call = payload["calls"][0]
    assert first_call["request_kind"] == "initial"
    assert first_call["turn_request"]["metadata"]["seat"] == 0
    assert first_call["provider_request"]["url"] == "https://example.invalid/v1/chat/completions"
    assert first_call["provider_response"]["status_code"] == 200


def test_poker_debug_llm_env_var_enables_logging_and_flag_can_disable_it(monkeypatch, tmp_path: Path) -> None:
    env_file, _ = _patch_runtime_paths(monkeypatch, tmp_path)
    lineup_file = tmp_path / "lineup.json"
    _write_live_env(env_file, seats=2, human_seat=1, configs=[_seat_config(2)])
    lineup_file.write_text(
        json.dumps(
            [
                {"type": "llm", "env_seat": 2, "name": "GPT Seat"},
                {"type": "rule", "name": "Rule Seat"},
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("POKER_DEBUG_LLM", "1")
    monkeypatch.setattr("pokercli.cli.provider_from_profile", lambda profile, api_key: LoggingProvider(profile))
    result = runner.invoke(app, ["simulate", "--hands", "1", "--lineup", str(lineup_file)])
    assert result.exit_code == 0
    files = sorted((tmp_path / "llm_debug").glob("*.json"))
    assert len(files) == 1
    for file in files:
        file.unlink()
    result = runner.invoke(app, ["simulate", "--hands", "1", "--lineup", str(lineup_file), "--no-debug-llm-log"])
    assert result.exit_code == 0
    assert list((tmp_path / "llm_debug").glob("*.json")) == []
