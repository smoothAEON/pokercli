from __future__ import annotations

import json
import os
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import questionary
import typer
from rich.console import Console
from rich.table import Table

from pokercli.agents import HumanController, LLMController, LLMStatusEvent, LiveLLMSeatError, RuleBotController
from pokercli.analytics import analytics_summary, compute_seat_analytics, write_summary_csv, write_summary_json
from pokercli.config import AppConfig, default_database_path, default_llm_debug_dir, load_config
from pokercli.debug_logs import SessionLLMDebugLogger
from pokercli.engine import ActionDecision, GameConfig, PokerGame
from pokercli.live_env import (
    DEFAULT_HUMAN_SEAT,
    DEFAULT_MAX_HANDS,
    DEFAULT_SEATS,
    DEFAULT_STACK_BB,
    DEFAULT_TEMPERATURE,
    DEFAULT_TIMEOUT_S,
    LiveSeatConfig,
    default_base_url_for_provider,
    default_model_for_provider,
    env_path,
    inspect_seat,
    load_env_values,
    seat_base_url_remove_keys,
    seat_key,
    seat_updates,
    table_defaults,
    table_updates,
    write_env_values,
)
from pokercli.llm import provider_from_profile
from pokercli.render import (
    LLMStatusRow,
    render_hand_history,
    render_llm_status_table,
    render_session_report,
    render_stored_hand_history,
    render_table,
)
from pokercli.store import PokerStorage

app = typer.Typer(help="Poker CLI simulator with LLM-controlled seats.")
console = Console()


class LiveSessionEnded(RuntimeError):
    """Raised when the user ends a live session during recovery."""


def banner() -> str:
    return "\n".join(
        [
            " ____       _             ____ _     ___ ",
            "|  _ \\ ___ | | _____ _ __/ ___| |   |_ _|",
            "| |_) / _ \\| |/ / _ \\ '__| |   | |    | | ",
            "|  __/ (_) |   <  __/ |  | |___| |___ | | ",
            "|_|   \\___/|_|\\_\\___|_|   \\____|_____|___|",
        ]
    )


def _storage(config: AppConfig) -> PokerStorage:
    database_path = config.database_path or str(default_database_path())
    return PokerStorage(database_path)


def _debug_llm_logging_enabled(explicit: bool | None) -> bool:
    if explicit is not None:
        return explicit
    return os.getenv("POKER_DEBUG_LLM") == "1"


def _required_opponent_seats(seats: int, human_seat: int) -> list[int]:
    return [seat_number for seat_number in range(1, seats + 1) if seat_number != human_seat]


def _resolve_live_table(
    env_values: dict[str, str],
    seats: int | None,
    human_seat: int | None,
    stack_bb: int | None,
    max_hands: int | None,
) -> tuple[int, int, int, int]:
    if human_seat not in (None, DEFAULT_HUMAN_SEAT):
        raise typer.BadParameter("human-seat is fixed to 1 for live play.")
    defaults = table_defaults(env_values)
    resolved_seats = seats or defaults["seats"] or DEFAULT_SEATS
    resolved_human_seat = DEFAULT_HUMAN_SEAT
    resolved_stack_bb = stack_bb or defaults["stack_bb"] or DEFAULT_STACK_BB
    resolved_max_hands = max_hands or defaults["max_hands"] or DEFAULT_MAX_HANDS
    if not 2 <= resolved_seats <= 6:
        raise typer.BadParameter("Live play supports 2 to 6 seats.")
    if resolved_stack_bb < 10:
        raise typer.BadParameter("stack-bb must be at least 10.")
    if resolved_max_hands < 1:
        raise typer.BadParameter("max-hands must be at least 1.")
    return resolved_seats, resolved_human_seat, resolved_stack_bb, resolved_max_hands


def _prompt_text_required(message: str, *, default: str | None = None, existing: str | None = None) -> str:
    raw = questionary.text(message, default=default).ask()
    if raw is None:
        raise typer.Exit(code=1)
    value = raw.strip()
    if value:
        return value
    if existing:
        return existing
    if default:
        return default
    raise typer.Exit(code=1)


def _prompt_password_required(message: str, *, existing: str | None = None) -> str:
    raw = questionary.password(message).ask()
    if raw is None:
        raise typer.Exit(code=1)
    if raw:
        return raw
    if existing:
        return existing
    raise typer.Exit(code=1)


def _prompt_int_required(message: str, *, default: int) -> int:
    raw = questionary.text(message, default=str(default)).ask()
    if raw is None:
        raise typer.Exit(code=1)
    value = raw.strip() or str(default)
    try:
        return int(value)
    except ValueError as exc:
        raise typer.BadParameter(f"Invalid integer for '{message}'.") from exc


def _prompt_float_required(message: str, *, default: float) -> float:
    raw = questionary.text(message, default=str(default)).ask()
    if raw is None:
        raise typer.Exit(code=1)
    value = raw.strip() or str(default)
    try:
        return float(value)
    except ValueError as exc:
        raise typer.BadParameter(f"Invalid number for '{message}'.") from exc


def _seed_seat_config(env_values: dict[str, str], seat_number: int) -> LiveSeatConfig | None:
    values = {
        suffix: env_values.get(seat_key(seat_number, suffix))
        for suffix in ("NAME", "PROVIDER", "MODEL", "API_KEY", "BASE_URL", "TIMEOUT_S", "TEMPERATURE")
    }
    if not any(values.values()):
        return None
    provider = (values["PROVIDER"] or "openrouter").strip().lower()
    timeout_default = values["TIMEOUT_S"] or str(DEFAULT_TIMEOUT_S)
    temperature_default = values["TEMPERATURE"] or str(DEFAULT_TEMPERATURE)
    try:
        timeout_s = float(timeout_default)
        temperature = float(temperature_default)
    except ValueError:
        timeout_s = DEFAULT_TIMEOUT_S
        temperature = DEFAULT_TEMPERATURE
    return LiveSeatConfig(
        seat_number=seat_number,
        name=(values["NAME"] or f"Bot {seat_number}").strip(),
        provider=provider,
        model=(values["MODEL"] or default_model_for_provider(provider)).strip(),
        api_key=(values["API_KEY"] or "").strip(),
        base_url=(values["BASE_URL"] or default_base_url_for_provider(provider) or "").strip() or default_base_url_for_provider(provider),
        timeout_s=timeout_s,
        temperature=temperature,
    )


def _prompt_provider(default_provider: str) -> str:
    provider = questionary.select(
        "Provider",
        choices=["openai", "anthropic", "openrouter", "nvidia", "openai-compatible"],
        default=default_provider,
    ).ask()
    if provider is None:
        raise typer.Exit(code=1)
    return provider


def _prompt_seat_config(seat_number: int, existing: LiveSeatConfig | None = None) -> LiveSeatConfig:
    provider_default = existing.provider if existing else "openrouter"
    provider = _prompt_provider(provider_default)
    name = _prompt_text_required(
        f"Seat {seat_number} name",
        default=existing.name if existing else f"Bot {seat_number}",
        existing=existing.name if existing else None,
    )
    model_default = (
        existing.model if existing and existing.provider == provider else default_model_for_provider(provider)
    )
    model = _prompt_text_required(f"Seat {seat_number} model", default=model_default, existing=existing.model if existing else None)
    api_key = _prompt_password_required(
        f"Seat {seat_number} API key",
        existing=existing.api_key if existing else None,
    )
    base_url = None
    if provider == "openai-compatible":
        base_url = _prompt_text_required(
            f"Seat {seat_number} base URL",
            default=existing.base_url if existing and existing.base_url else "",
            existing=existing.base_url if existing else None,
        )
    elif provider == "openrouter":
        base_url = default_base_url_for_provider(provider)
    timeout_s = _prompt_float_required(
        f"Seat {seat_number} timeout seconds",
        default=existing.timeout_s if existing else DEFAULT_TIMEOUT_S,
    )
    temperature = _prompt_float_required(
        f"Seat {seat_number} temperature",
        default=existing.temperature if existing else DEFAULT_TEMPERATURE,
    )
    return LiveSeatConfig(
        seat_number=seat_number,
        name=name,
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
        timeout_s=timeout_s,
        temperature=temperature,
    )


def _write_live_table(
    seats: int,
    human_seat: int,
    stack_bb: int,
    max_hands: int,
    seat_configs: dict[int, LiveSeatConfig],
) -> None:
    _write_live_table_defaults(seats, human_seat, stack_bb, max_hands)
    _write_live_seat_configs(seat_configs)


def _write_live_table_defaults(seats: int, human_seat: int, stack_bb: int, max_hands: int) -> None:
    write_env_values(table_updates(seats, human_seat, stack_bb, max_hands))


def _write_live_seat_configs(seat_configs: dict[int, LiveSeatConfig]) -> None:
    if not seat_configs:
        return
    updates: dict[str, str] = {}
    remove_keys: list[str] = []
    for seat_config in seat_configs.values():
        updates.update(seat_updates(seat_config))
        remove_keys.extend(seat_base_url_remove_keys(seat_config.seat_number, seat_config.provider))
    write_env_values(updates, remove_keys=remove_keys)


def _ensure_live_seat_configs(
    env_values: dict[str, str],
    seats: int,
    human_seat: int,
) -> tuple[dict[str, str], dict[int, LiveSeatConfig]]:
    configs: dict[int, LiveSeatConfig] = {}
    missing: list[int] = []
    for seat_number in _required_opponent_seats(seats, human_seat):
        config, _missing_fields = inspect_seat(env_values, seat_number)
        if config is None:
            missing.append(seat_number)
        else:
            configs[seat_number] = config
    if not missing:
        return env_values, configs
    console.print("Live play requires a configured LLM for every opponent seat. Starting seat onboarding.")
    prompted: dict[int, LiveSeatConfig] = {}
    for seat_number in missing:
        prompted[seat_number] = _prompt_seat_config(seat_number, _seed_seat_config(env_values, seat_number))
    _write_live_seat_configs(prompted)
    reloaded = load_env_values()
    for seat_number in missing:
        config, missing_fields = inspect_seat(reloaded, seat_number)
        if config is None:
            raise typer.BadParameter(
                f"Seat {seat_number} is still incomplete after onboarding: {', '.join(missing_fields)}"
            )
        configs[seat_number] = config
    return reloaded, configs


def _build_live_llm_controller(
    seat_config: LiveSeatConfig,
    *,
    status_callback=None,
) -> LLMController:
    provider = _provider_from_live_seat_config(seat_config)
    return LLMController(
        seat_name=seat_config.name,
        provider=provider,
        failure_mode="raise",
        status_callback=status_callback,
    )


def _provider_from_live_seat_config(
    seat_config: LiveSeatConfig,
    *,
    force_temperature_zero: bool = False,
):
    profile = seat_config.to_profile()
    if force_temperature_zero:
        profile = replace(profile, temperature=0.0)
    return provider_from_profile(profile, seat_config.api_key)


def _controllers_from_live_seats(
    seats: int,
    human_seat: int,
    seat_configs: dict[int, LiveSeatConfig],
    *,
    status_callback=None,
) -> tuple[list[str], dict[int, object]]:
    names: list[str] = []
    controllers: dict[int, object] = {}
    for seat_index in range(seats):
        seat_number = seat_index + 1
        if seat_number == human_seat:
            names.append("You")
            controllers[seat_index] = HumanController()
            continue
        seat_config = seat_configs[seat_number]
        names.append(seat_config.name)
        controllers[seat_index] = _build_live_llm_controller(seat_config, status_callback=status_callback)
    return names, controllers


def _record_llm_logs(
    storage: PokerStorage,
    llm_debug_logger: SessionLLMDebugLogger | None,
    controllers: dict[int, object],
) -> None:
    for controller in controllers.values():
        if not isinstance(controller, LLMController):
            continue
        for log in controller.turn_logs:
            storage.record_llm_turn(
                session_id=log.session_id,
                hand_no=log.hand_no,
                seat=log.seat,
                provider=log.provider,
                model=log.model,
                success=log.success,
                request_payload=log.request_payload(),
                response_payload=log.response_payload(),
                error_text=log.error,
            )
            if llm_debug_logger is not None:
                llm_debug_logger.record_call(log.to_dict())
        controller.turn_logs.clear()


def _require_env_seat_config_for_simulation(env_values: dict[str, str], env_seat: int) -> LiveSeatConfig:
    seat_config, missing_fields = inspect_seat(env_values, env_seat)
    if seat_config is None:
        missing = ", ".join(missing_fields) if missing_fields else "missing seat block"
        raise typer.BadParameter(f"Lineup env_seat {env_seat} is incomplete in {env_path()}: {missing}")
    return seat_config


def _controllers_from_env_lineup(
    lineup: list[dict[str, Any]],
    env_values: dict[str, str],
    force_temperature_zero: bool,
) -> tuple[list[str], dict[int, object]]:
    names = []
    controllers: dict[int, object] = {}
    for seat, spec in enumerate(lineup):
        controller_type = spec.get("type", "rule")
        if controller_type == "rule":
            name = spec.get("name", f"Seat {seat + 1}")
            names.append(name)
            controllers[seat] = RuleBotController(name=name, seed=spec.get("seed", seat))
            continue
        if controller_type != "llm":
            raise typer.BadParameter(f"Unsupported lineup type: {controller_type}")
        try:
            env_seat = int(spec["env_seat"])
        except KeyError as exc:
            raise typer.BadParameter("LLM lineup entries require an env_seat field.") from exc
        except (TypeError, ValueError) as exc:
            raise typer.BadParameter(f"Invalid env_seat for lineup seat {seat + 1}.") from exc
        if env_seat < 1:
            raise typer.BadParameter(f"env_seat must be >= 1 for lineup seat {seat + 1}.")
        seat_config = _require_env_seat_config_for_simulation(env_values, env_seat)
        name = spec.get("name", seat_config.name)
        names.append(name)
        provider = _provider_from_live_seat_config(seat_config, force_temperature_zero=force_temperature_zero)
        controllers[seat] = LLMController(seat_name=name, provider=provider)
    return names, controllers


def _controller_lineup(controllers: dict[int, object]) -> tuple[str, ...]:
    return tuple(type(controller).__name__ for controller in controllers.values())


def _display_summary(summary: dict[str, Any]) -> None:
    table = Table(title="Session Summary")
    table.add_column("Seat")
    table.add_column("Player")
    table.add_column("PnL")
    table.add_column("BB/100")
    table.add_column("VPIP")
    table.add_column("PFR")
    table.add_column("3B")
    table.add_column("SD Win")
    table.add_column("Max DD")
    table.add_column("Vol")
    table.add_column("RoR")
    for seat, metric in summary["seats"].items():
        table.add_row(
            str(seat),
            metric["player_name"],
            str(metric["pnl"]),
            f"{metric['bb_per_100']:.2f}",
            f"{metric['vpip']:.2%}",
            f"{metric['pfr']:.2%}",
            f"{metric['three_bet_rate']:.2%}",
            f"{metric['showdown_win_rate']:.2%}",
            str(metric["max_drawdown"]),
            f"{metric['volatility']:.2f}",
            f"{metric['risk_of_ruin']:.2%}",
        )
    console.print(table)


def _write_live_session_report(
    game: PokerGame,
    seat_metrics: dict[int, Any],
    end_reason: str,
) -> Path:
    report_path = Path("reports") / f"pokercli-session-{game.session_id}.txt"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        render_session_report(
            session_id=game.session_id,
            histories=game.hand_histories,
            seat_metrics=seat_metrics,
            game_config=game.config,
            end_reason=end_reason,
            final_stacks={seat: player.stack for seat, player in game.seats.items()},
            seat_names={seat: player.name for seat, player in game.seats.items()},
        ),
        encoding="utf-8",
    )
    return report_path


def _initial_status_rows(seat_configs: dict[int, LiveSeatConfig]) -> dict[int, LLMStatusRow]:
    return {
        seat_number - 1: LLMStatusRow(
            seat=seat_number - 1,
            name=seat_config.name,
            provider=seat_config.provider,
            model=seat_config.model,
            status="idle",
            note="",
        )
        for seat_number, seat_config in seat_configs.items()
    }


def _print_llm_status(rows: dict[int, LLMStatusRow]) -> None:
    console.print(render_llm_status_table(list(rows.values())))


def _refresh_pending_statuses(game: PokerGame, rows: dict[int, LLMStatusRow]) -> None:
    state = game.require_state()
    pending = set(state.pending_to_act)
    for seat, row in rows.items():
        player = state.seats[seat]
        if player.hole_cards is None or player.folded or player.all_in:
            if row.status != "failed":
                row.status = "idle"
                row.note = ""
            continue
        if seat in pending and row.status not in {"requesting", "retrying", "responded"}:
            row.status = "queued"
            row.note = "waiting turn"


def _status_callback(rows: dict[int, LLMStatusRow], visibility: dict[str, bool]):
    def callback(event: LLMStatusEvent) -> None:
        row = rows[event.seat]
        row.name = event.seat_name
        row.provider = event.provider
        row.model = event.model
        row.status = event.status
        row.note = event.note
        if visibility["visible"]:
            _print_llm_status(rows)

    return callback


def _reset_status_rows(rows: dict[int, LLMStatusRow]) -> None:
    for row in rows.values():
        row.status = "idle"
        row.note = ""


def _handle_live_llm_failure(
    controllers: dict[int, object],
    rows: dict[int, LLMStatusRow],
    seat_configs: dict[int, LiveSeatConfig],
    seat_index: int,
    error: LiveLLMSeatError,
) -> dict[int, LiveSeatConfig]:
    console.print(f"LLM seat failure for {error.seat_name}: {error.reason}")
    choice = questionary.select(
        "Choose how to recover this seat",
        choices=["Retry request", "Reconfigure seat LLM", "End session"],
    ).ask()
    if choice == "Retry request":
        controller = controllers[seat_index]
        if isinstance(controller, LLMController):
            controller.reset_failures()
        rows[seat_index].status = "queued"
        rows[seat_index].note = "retry requested"
        return seat_configs
    if choice == "Reconfigure seat LLM":
        seat_number = seat_index + 1
        updated = _prompt_seat_config(seat_number, seat_configs[seat_number])
        seat_configs[seat_number] = updated
        _write_live_seat_configs({seat_number: updated})
        controllers[seat_index] = _build_live_llm_controller(updated, status_callback=controllers[seat_index].status_callback if isinstance(controllers[seat_index], LLMController) else None)
        rows[seat_index] = LLMStatusRow(
            seat=seat_index,
            name=updated.name,
            provider=updated.provider,
            model=updated.model,
            status="queued",
            note="reconfigured",
        )
        return seat_configs
    raise LiveSessionEnded("Live session ended after an LLM failure.")


@app.command()
def setup(
    seats: int | None = typer.Option(None, min=2, max=6),
    human_seat: int | None = typer.Option(None, min=1),
    stack_bb: int | None = typer.Option(None, min=10),
    max_hands: int | None = typer.Option(None, min=1),
) -> None:
    """Write or update live-play seat configuration in `.env`."""
    console.print(banner())
    env_values = load_env_values()
    resolved_seats, resolved_human_seat, resolved_stack_bb, resolved_max_hands = _resolve_live_table(
        env_values,
        seats,
        human_seat,
        stack_bb,
        max_hands,
    )
    resolved_seats = _prompt_int_required("Seat count", default=resolved_seats)
    resolved_stack_bb = _prompt_int_required("Starting stack in BB", default=resolved_stack_bb)
    resolved_max_hands = _prompt_int_required("Max hands per session", default=resolved_max_hands)
    if not 2 <= resolved_seats <= 6:
        raise typer.BadParameter("Seat count must be between 2 and 6.")
    seat_configs = {
        seat_number: _prompt_seat_config(seat_number, _seed_seat_config(env_values, seat_number))
        for seat_number in _required_opponent_seats(resolved_seats, resolved_human_seat)
    }
    _write_live_table(
        resolved_seats,
        resolved_human_seat,
        resolved_stack_bb,
        resolved_max_hands,
        seat_configs,
    )
    console.print(f"Saved live seat configuration to {env_path()}")


@app.command()
def play(
    seats: int | None = typer.Option(None, min=2, max=6),
    human_seat: int | None = typer.Option(None, min=1),
    stack_bb: int | None = typer.Option(None, min=10),
    max_hands: int | None = typer.Option(None, min=1),
    debug_llm_log: bool | None = typer.Option(
        None,
        "--debug-llm-log/--no-debug-llm-log",
        help="Write per-session JSON debug logs for every LLM provider call.",
    ),
) -> None:
    """Play a single-player table where every opponent seat has its own LLM."""
    console.print(banner())
    app_config = load_config()
    env_values = load_env_values()
    resolved_seats, resolved_human_seat, resolved_stack_bb, resolved_max_hands = _resolve_live_table(
        env_values,
        seats,
        human_seat,
        stack_bb,
        max_hands,
    )
    if seats is None:
        resolved_seats = _prompt_int_required("How many players?", default=resolved_seats)
        if not 2 <= resolved_seats <= 6:
            raise typer.BadParameter("Seat count must be between 2 and 6.")
    env_values, seat_configs = _ensure_live_seat_configs(
        env_values,
        resolved_seats,
        resolved_human_seat,
    )
    _write_live_table_defaults(
        resolved_seats,
        resolved_human_seat,
        resolved_stack_bb,
        resolved_max_hands,
    )
    status_rows = _initial_status_rows(seat_configs)
    status_visibility = {"visible": False}
    names, controllers = _controllers_from_live_seats(
        resolved_seats,
        resolved_human_seat,
        seat_configs,
        status_callback=_status_callback(status_rows, status_visibility),
    )
    controller_lineup = _controller_lineup(controllers)
    game_config = GameConfig(
        seat_count=resolved_seats,
        small_blind=50,
        big_blind=100,
        starting_stack=resolved_stack_bb * 100,
        max_hands=resolved_max_hands,
        controller_lineup=controller_lineup,
    )
    session_config = asdict(game_config)
    game = PokerGame(
        game_config,
        seat_names=names,
        controllers=controller_lineup,
    )
    storage = _storage(app_config)
    llm_debug_logger = (
        SessionLLMDebugLogger(
            session_id=game.session_id,
            mode="play",
            config=session_config,
            log_dir=default_llm_debug_dir(),
        )
        if _debug_llm_logging_enabled(debug_llm_log)
        else None
    )
    human_index = resolved_human_seat - 1
    end_reason: str | None = None
    try:
        storage.record_session(game.session_id, "play", session_config, game.rng.seed_value)
        while game.can_start_hand():
            _reset_status_rows(status_rows)
            status_visibility["visible"] = False
            try:
                def on_human_view(view) -> None:
                    console.print(render_table(view))

                def on_llm_error(seat: int, error: LiveLLMSeatError) -> None:
                    nonlocal seat_configs
                    seat_configs = _handle_live_llm_failure(
                        controllers,
                        status_rows,
                        seat_configs,
                        seat,
                        error,
                    )
                    if status_visibility["visible"]:
                        _print_llm_status(status_rows)

                def on_action_applied(seat: int, decision: ActionDecision) -> None:
                    if isinstance(controllers[seat], HumanController):
                        status_visibility["visible"] = True
                        _refresh_pending_statuses(game, status_rows)
                        _print_llm_status(status_rows)
                        return
                    row = status_rows[seat]
                    row.status = "acted"
                    row.note = decision.normalized_action().value
                    _refresh_pending_statuses(game, status_rows)
                    if status_visibility["visible"]:
                        _print_llm_status(status_rows)

                _run_hand(
                    game,
                    controllers,
                    interactive=True,
                    on_human_view=on_human_view,
                    on_llm_error=on_llm_error,
                    on_action_applied=on_action_applied,
                )
            except LiveSessionEnded as exc:
                if game.state is not None:
                    _record_llm_logs(storage, llm_debug_logger, controllers)
                console.print(str(exc))
                end_reason = "llm-failure"
                break
            history = game.hand_histories[-1]
            storage.record_hand(history)
            _record_llm_logs(storage, llm_debug_logger, controllers)
            console.print(render_hand_history(history))
            if game.seats[human_index].stack <= 0:
                console.print("You are out of chips.")
                end_reason = "human-bust"
                break
            if not game.can_start_hand():
                end_reason = "max-hands" if game.hand_no >= game.config.max_hands else "table-ended"
                break
            keep_going = questionary.confirm("Play another hand?", default=True).ask()
            if not keep_going:
                end_reason = "user-stopped"
                break
        if end_reason is None:
            end_reason = "max-hands" if game.hand_no >= game.config.max_hands else "table-ended"
        seat_metrics = compute_seat_analytics(game.hand_histories, game.config.big_blind)
        summary = analytics_summary(game.hand_histories, game.config.big_blind)
        storage.record_summary(game.session_id, summary)
        _display_summary(summary)
        report_path = _write_live_session_report(game, seat_metrics, end_reason)
        console.print(f"Session report saved to {report_path}")
    finally:
        try:
            if llm_debug_logger is not None:
                llm_debug_logger.finalize()
        finally:
            storage.close()


def _run_hand(
    game: PokerGame,
    controllers: dict[int, object],
    *,
    interactive: bool,
    on_human_view=None,
    on_llm_error=None,
    on_action_applied=None,
) -> None:
    game.start_hand()
    state = game.require_state()
    while not state.hand_complete:
        if not state.pending_to_act:
            game._auto_advance_if_no_decisions()  # noqa: SLF001
            continue
        seat = state.pending_to_act[0]
        controller = controllers[seat]
        view = game.build_seat_view(seat)
        if interactive and isinstance(controller, HumanController):
            if on_human_view is None:
                console.print(render_table(view))
            else:
                on_human_view(view)
        try:
            decision = controller.act(view)
        except LiveLLMSeatError as exc:
            if on_llm_error is None:
                raise
            on_llm_error(seat, exc)
            state = game.require_state()
            continue
        if not isinstance(decision, ActionDecision):
            raise typer.Exit(code=1)
        game.apply_action(seat, decision)
        if on_action_applied is not None:
            on_action_applied(seat, decision)
        state = game.require_state()


@app.command()
def simulate(
    hands: int = typer.Option(1_000, min=1),
    seed: int = typer.Option(1),
    lineup: str | None = typer.Option(None, help="Path to a JSON lineup file."),
    json_out: str | None = typer.Option(None),
    csv_out: str | None = typer.Option(None),
    debug_llm_log: bool | None = typer.Option(
        None,
        "--debug-llm-log/--no-debug-llm-log",
        help="Write per-session JSON debug logs for every LLM provider call.",
    ),
) -> None:
    """Run a batch simulation or backtest."""
    console.print(banner())
    config = load_config()
    if lineup:
        lineup_data = json.loads(Path(lineup).read_text(encoding="utf-8"))
    else:
        lineup_data = [{"type": "rule", "name": f"Bot {seat + 1}"} for seat in range(6)]
    env_values = load_env_values()
    names, controllers = _controllers_from_env_lineup(lineup_data, env_values, force_temperature_zero=True)
    controller_lineup = _controller_lineup(controllers)
    game_config = GameConfig(
        seat_count=len(lineup_data),
        small_blind=50,
        big_blind=100,
        starting_stack=10_000,
        max_hands=hands,
        seed=seed,
        controller_lineup=controller_lineup,
    )
    session_config = asdict(game_config)
    game = PokerGame(
        game_config,
        seat_names=names,
        controllers=controller_lineup,
    )
    storage = _storage(config)
    llm_debug_logger = (
        SessionLLMDebugLogger(
            session_id=game.session_id,
            mode="simulate",
            config=session_config,
            log_dir=default_llm_debug_dir(),
        )
        if _debug_llm_logging_enabled(debug_llm_log)
        else None
    )
    try:
        storage.record_session(game.session_id, "simulate", session_config, game.rng.seed_value)
        while game.can_start_hand():
            _run_hand(game, controllers, interactive=False)
            history = game.hand_histories[-1]
            storage.record_hand(history)
            _record_llm_logs(storage, llm_debug_logger, controllers)
        summary = analytics_summary(game.hand_histories, game.config.big_blind)
        storage.record_summary(game.session_id, summary)
        _display_summary(summary)
        if json_out:
            write_summary_json(json_out, summary)
        if csv_out:
            write_summary_csv(csv_out, compute_seat_analytics(game.hand_histories, game.config.big_blind))
    finally:
        try:
            if llm_debug_logger is not None:
                llm_debug_logger.finalize()
        finally:
            storage.close()


@app.command()
def replay(
    session_id: str | None = typer.Option(None),
    hand_id: str | None = typer.Option(None),
) -> None:
    """Replay a stored hand or the latest hand from a session."""
    config = load_config()
    storage = _storage(config)
    try:
        hand = storage.load_hand(session_id=session_id, hand_id=hand_id)
    finally:
        storage.close()
    console.print(render_stored_hand_history(hand))


if __name__ == "__main__":
    app()
