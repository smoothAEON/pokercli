# PokerCLI 🃏

<div align="center">

**CLI Texas Hold'em poker simulator with LLM-controlled opponent seats and batch backtesting.**

[![Python](https://img.shields.io/badge/Python-3.13%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![LLM Poker](https://img.shields.io/badge/LLM_Poker-Play_Against_AI-purple?logo=openai)](https://github.com)
[![Providers](https://img.shields.io/badge/Providers-5-orange?logo=openai&logoColor=white)](#supported-llm-providers)
[![Poker](https://img.shields.io/badge/Game-Texas_Hold'em-red?logo=clubs)](https://en.wikipedia.org/wiki/Texas_hold_%27em)
[![CLI](https://img.shields.io/badge/Interface-CLI_%2B_Rich_TUI-cyan?logo=windowsterminal)](https://rich.readthedocs.io/)

</div>

---

## Table of Contents

- [What is PokerCLI?](#what-is-pokercli)
- [Quick Start (30 seconds)](#quick-start-30-seconds)
- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
  - [Windows](#windows)
  - [macOS](#macos)
  - [Linux](#linux)
  - [Verify Installation](#verify-installation)
- [Setup & Configuration](#setup--configuration)
  - [The `.env` File](#the-env-file)
  - [`.env` Reference (Every Key Explained)](#env-reference-every-key-explained)
  - [Supported LLM Providers](#supported-llm-providers)
  - [Getting API Keys](#getting-api-keys)
- [Commands](#commands)
  - [`play` — Live Play](#play--live-play)
  - [`setup` — Pre-Bootstrap Seats](#setup--pre-bootstrap-seats)
  - [`simulate` — Batch Backtesting](#simulate--batch-backtesting)
  - [`replay` — Replay Stored Hands](#replay--replay-stored-hands)
- [Analytics & Metrics](#analytics--metrics)
- [LLM Debug Logs](#llm-debug-logs)
- [Architecture](#architecture)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [License](#license)

---

## What is PokerCLI?

PokerCLI is a **terminal-based Texas Hold'em poker game** where you (the human) sit at **Seat 1** and every other seat is controlled by an **LLM** — OpenAI, Anthropic, OpenRouter, NVIDIA NIM, or any OpenAI-compatible endpoint.

It's also a **backtesting engine**: run thousands of hands with mixed LLM + rule-bot lineups, get full analytics (VPIP, PFR, 3-bet rate, PnL, max drawdown, risk of ruin), and export results to CSV or JSON.

```
 ____       _             ____ _     ___
|  _ \ ___ | | _____ _ __/ ___| |   |_ _|
| |_) / _ \| |/ / _ \ '__| |   | |    | |
|  __/ (_) |   <  __/ |  | |___| |___ | |
|_|   \___/|_|\_\___|_|   \____|_____|___|
```

### You play. The LLMs play. Every seat sees only what it should.

PokerCLI enforces **strict information segmentation** — each LLM seat only receives its own hole cards plus the public board. No peeking at opponents' hands. This is verified by the `test_redaction.py` test suite.

---

## Quick Start (30 seconds)

```bash
# 1. Clone and install
git clone https://github.com/smoothaeon/pokercli.git
cd pokercli
pip install -e ".[dev]"

# 2. Launch — it will ask how many players, then walk you through seat setup
python -m pokercli play
```

If you already have `.env` configured: just run `python -m pokercli play` and start playing.

On Windows, double-click `play_poker.bat`.

---

## Features

| Feature | Description |
|---|---|
| **Live human vs LLM** | You at Seat 1, LLMs at every other seat. Real-time status table shows each bot's state. |
| **5 LLM providers** | OpenAI, Anthropic, OpenRouter, NVIDIA NIM, and any OpenAI-compatible endpoint. |
| **Provider adapter pattern** | All LLMs unified behind a single interface. Swap providers per seat. |
| **Strict information segmentation** | Each LLM only sees its own hole cards + public board state. Verified by tests. |
| **Interactive `.env` onboarding** | No manual config needed — `play` and `setup` prompt you for every seat. |
| **Batch simulation** | Run thousands of hands with mixed LLM + rule-bot lineups. Reproducible with seeded RNG. |
| **Full analytics** | VPIP, PFR, 3-bet rate, PnL, BB/100, showdown win rate, max drawdown, volatility, risk of ruin. |
| **SQLite session storage** | Every hand, action, and LLM call is stored. Replay any session later. |
| **LLM debug logging** | Optional per-session JSON logs with full request/response payloads (secrets redacted). |
| **Live LLM failure recovery** | If a bot's API call fails, you can retry, reconfigure the seat, or end the session. |
| **RuleBot fallback** | Every LLM seat has a built-in rule-based bot fallback. Configurable failure handling. |
| **Side pot support** | Multi-way all-ins with short stacks are handled correctly. |
| **Session memory** | LLM seats maintain context across hands (default 5-hand window). |
| **Rich TUI** | Beautiful terminal UI built with [Rich](https://github.com/Textualize/rich). |
| **Cross-platform** | Windows, macOS, Linux. Data stored via `platformdirs`. |
| **CSV/JSON export** | Export simulation results for further analysis. |

---

## Requirements

### Hard Requirements

- **Python 3.13 or newer** (required — the codebase uses modern Python features)
- **pip** (included with Python)

### For LLM Seats (Live Play / LLM Simulation)

You need at least one LLM API key from any of:

| Provider | Free Tier? | Get a Key |
|---|---|---|
| **OpenAI** | No (pay-as-you-go) | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| **Anthropic** | No (pay-as-you-go) | [console.anthropic.com](https://console.anthropic.com/) |
| **OpenRouter** | No (pay-as-you-go, multi-model) | [openrouter.ai/keys](https://openrouter.ai/keys) |
| **NVIDIA NIM** | **Yes** (free tier available) | [build.nvidia.com](https://build.nvidia.com/) |
| **OpenAI-Compatible** | Depends on provider | Any endpoint with `/chat/completions` |

> **If you don't want to pay:** Use **NVIDIA NIM** (free tier) or **OpenRouter** with a free model. See the [Getting API Keys](#getting-api-keys) section below.

### For RuleBot-Only Simulation

No API keys needed at all. Simulate with rule-based bots only — no LLM costs.

---

## Installation

### Windows

**Option A: Use the launcher (easiest)**
1. Double-click `play_poker.bat`
2. It auto-detects Python, installs dependencies if needed, and launches the game.

**Option B: Command line**
```powershell
# Make sure Python 3.13+ is in your PATH
python --version  # must be 3.13 or higher

# Install
pip install -e ".[dev]"

# Run
python -m pokercli play
```

If Python is not found:
1. Download from [python.org](https://www.python.org/downloads/) (choose "Add Python to PATH" during install)
2. Open a **new** PowerShell/Command Prompt window
3. Run the commands above

### macOS

```bash
# Install Python 3.13+ (if needed)
brew install python@3.13

# Clone and install
git clone https://github.com/smoothaeon/pokercli.git
cd pokercli
pip install -e ".[dev]"

# Run
python -m pokercli play
```

### Linux

```bash
# Install Python 3.13+ (Ubuntu/Debian example)
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update
sudo apt install python3.13 python3.13-venv python3.13-dev -y

# Clone and install
git clone https://github.com/smoothaeon/pokercli.git
cd pokercli
python3.13 -m pip install -e ".[dev]"

# Run
python3.13 -m pokercli play
```

### Verify Installation

```bash
python -m pokercli --help
```

You should see:
```
Usage: python -m pokercli [OPTIONS] COMMAND [ARGS]...

Poker CLI simulator with LLM-controlled seats.

Commands:
  play       Play a single-player table where every opponent seat has its own LLM.
  replay     Replay a stored hand or the latest hand from a session.
  setup      Write or update live-play seat configuration in `.env`.
  simulate   Run a batch simulation or backtest.
```

---

## Setup & Configuration

PokerCLI stores all live-play configuration in a `.env` file at the root of the repository. You never need to edit this file manually — the `play` and `setup` commands walk you through every setting interactively.

### The `.env` File

**Location:** `<repo>/.env` (default)  
**Override:** Set `POKER_ENV_PATH=/path/to/custom.env` before running.

The `.env` file is **gitignored** — your API keys are never committed. A template (`.env.example`) is provided for reference.

### `.env` Reference (Every Key Explained)

#### Global Table Settings

| Key | Description | Default | Valid Range |
|---|---|---|---|
| `POKER_SEATS` | Total players at the table (you + bots) | `6` | `2` – `6` |
| `POKER_HUMAN_SEAT` | Which seat you occupy | `1` (always) | `1` (fixed) |
| `POKER_STACK_BB` | Starting stack in big blinds | `100` | ≥ `10` |
| `POKER_MAX_HANDS` | Max hands per session | `50` | ≥ `1` |

#### Per-Seat LLM Settings

For each opponent seat (seat number `N`), seven keys configure the LLM:

| Key | Description | Example | Required? |
|---|---|---|---|
| `POKER_SEAT_N_TYPE` | Controller type | `llm` | ✅ |
| `POKER_SEAT_N_NAME` | Display name | `GPT-4o Bot` | ✅ |
| `POKER_SEAT_N_PROVIDER` | LLM provider | `openai` | ✅ |
| `POKER_SEAT_N_MODEL` | Model ID | `gpt-4o` | ✅ |
| `POKER_SEAT_N_API_KEY` | API key | `sk-...` | ✅ |
| `POKER_SEAT_N_TIMEOUT_S` | Timeout in seconds | `30` | ✅ |
| `POKER_SEAT_N_TEMPERATURE` | LLM temperature (`0` = deterministic) | `0` | ✅ |
| `POKER_SEAT_N_BASE_URL` | Custom endpoint URL | `https://api.example.com/v1` | Only for `openai-compatible` |

**Example `.env` for a 3-player table (you + 2 bots):**

```dotenv
POKER_SEATS=3
POKER_HUMAN_SEAT=1
POKER_STACK_BB=100
POKER_MAX_HANDS=25

POKER_SEAT_2_TYPE=llm
POKER_SEAT_2_NAME=OpenRouter GPT
POKER_SEAT_2_PROVIDER=openrouter
POKER_SEAT_2_MODEL=openai/gpt-4o
POKER_SEAT_2_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxx
POKER_SEAT_2_TIMEOUT_S=30
POKER_SEAT_2_TEMPERATURE=0

POKER_SEAT_3_TYPE=llm
POKER_SEAT_3_NAME=NVIDIA Llama
POKER_SEAT_3_PROVIDER=nvidia
POKER_SEAT_3_MODEL=nvidia/llama-3.1-nemotron-nano-8b-v1
POKER_SEAT_3_API_KEY=nvapi-xxxxxxxxxxxxxxxxxxxxxxxx
POKER_SEAT_3_TIMEOUT_S=30
POKER_SEAT_3_TEMPERATURE=0
```

### Supported LLM Providers

| Provider | `.env` Value | Default Model | Default Endpoint | Notes |
|---|---|---|---|---|
| **OpenAI** | `openai` | `gpt-5.4-mini` | `https://api.openai.com/v1` | Standard `/chat/completions` |
| **Anthropic** | `anthropic` | `claude-sonnet-4-5` | `https://api.anthropic.com` | Uses `/v1/messages` |
| **OpenRouter** | `openrouter` | `openai/gpt-4o` | `https://openrouter.ai/api/v1` | Multi-model gateway |
| **NVIDIA NIM** | `nvidia` | `nvidia/llama-3.1-nemotron-nano-8b-v1` | `https://integrate.api.nvidia.com/v1` | Free tier available |
| **OpenAI-Compatible** | `openai-compatible` | `gpt-5.4-mini` | *Must set `BASE_URL`* | Any `/chat/completions` endpoint |

### Getting API Keys

<details>
<summary><b>OpenAI</b></summary>

1. Go to [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
2. Sign up or log in
3. Click "Create new secret key"
4. Copy the key (starts with `sk-proj-...` or `sk-...`)
5. Add billing if you haven't already
</details>

<details>
<summary><b>Anthropic</b></summary>

1. Go to [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys)
2. Sign up or log in
3. Click "Create Key"
4. Copy the key (starts with `sk-ant-...`)
5. Add credits/billing
</details>

<details>
<summary><b>OpenRouter</b></summary>

1. Go to [openrouter.ai/keys](https://openrouter.ai/keys)
2. Sign up or log in
3. Click "Create Key"
4. Copy the key (starts with `sk-or-v1-...`)
5. Add credits — you can start with as little as $5
6. Browse available models at [openrouter.ai/models](https://openrouter.ai/models)

**Tip:** OpenRouter gives you access to 200+ models. You can use GPT-4o, Claude, Llama, and more — all with one API key. Model IDs look like `openai/gpt-4o` or `anthropic/claude-sonnet-4-5`.
</details>

<details>
<summary><b>NVIDIA NIM (Free Tier Available!)</b></summary>

1. Go to [build.nvidia.com](https://build.nvidia.com/)
2. Sign up (free account)
3. Go to any model page (e.g., [Llama 3.1 Nemotron Nano 8B](https://build.nvidia.com/nvidia/llama-3_1-nemotron-nano-8b-v1))
4. Click "Get API Key"
5. Copy the key (starts with `nvapi-...`)
6. Free tier: 1,000 requests per month (plenty for casual play)
</details>

<details>
<summary><b>OpenAI-Compatible (self-hosted / third-party)</b></summary>

Any endpoint that implements `/chat/completions` works. Examples:
- **Ollama** (local): `http://localhost:11434/v1`
- **vLLM** (self-hosted): `http://your-server:8000/v1`
- **Together AI**: `https://api.together.xyz/v1`
- **Groq**: `https://api.groq.com/openai/v1`

You must set `POKER_SEAT_N_BASE_URL` to the endpoint URL.
</details>

---

## Commands

### `play` — Live Play

```bash
python -m pokercli play
```

This launches the main game. Here's what happens step by step:

1. **Banner** — the PokerCLI ASCII art appears.
2. **Seat count** — If not in `.env`, it asks "How many players?" (2–6). Seat 1 is always you.
3. **Seat onboarding** — For any opponent seat missing from `.env`, it prompts:
   - Provider (choose from list)
   - Name (display name)
   - Model (auto-suggests based on provider)
   - API key (masked input)
   - Timeout (default 30s)
   - Temperature (default 0 = deterministic)
4. **Game starts** — Blinds are posted, cards are dealt.

#### During a hand:

- **Your turn:** You see the board, your hole cards, stack, pot, and legal actions. Type actions like:
  - `c` or `call` — call the current bet
  - `k` or `check` — check
  - `f` or `fold` — fold
  - `r 300` or `raise 300` — raise to 300
  - `b 200` or `bet 200` — bet 200
  - `all` or `all-in` — go all-in

- **LLM status table:** After you act, a table shows each bot's status:
  - `idle` — waiting
  - `queued` — waiting for its turn
  - `requesting` — calling the API
  - `retrying` — retrying after an invalid response
  - `responded` — received a valid response
  - `acted` — action applied
  - `failed` — error occurred

#### LLM Failure Recovery:

If an LLM seat fails (API error, invalid response, etc.), you get three choices:
1. **Retry request** — Try the same API call again
2. **Reconfigure seat LLM** — Change provider/model/key for this seat
3. **End session** — Stop the game

#### Between hands:

After each hand, you see:
- The hand history (all actions, board, results)
- Winner and pot distribution
- "Play another hand?" prompt

When the session ends (max hands reached, you bust, or you stop), you get:
- **Session summary table** — PnL, BB/100, VPIP, PFR, 3-bet, showdown win rate, max drawdown, volatility, risk of ruin for every seat
- **Session report** saved to `reports/pokercli-session-<uuid>.txt`

#### Options:

```bash
# Specify seat count upfront (skip the prompt)
python -m pokercli play --seats 3

# Start with 150 BB instead of 100
python -m pokercli play --stack-bb 150

# Play at most 20 hands
python -m pokercli play --max-hands 20

# Enable per-session LLM debug logs
python -m pokercli play --debug-llm-log

# Disable debug logs even if POKER_DEBUG_LLM=1 is set
python -m pokercli play --no-debug-llm-log

# Use a custom .env file
set POKER_ENV_PATH=C:\my\custom.env && python -m pokercli play

# Combine everything
python -m pokercli play --seats 4 --stack-bb 200 --max-hands 10 --debug-llm-log
```

### `setup` — Pre-Bootstrap Seats

```bash
python -m pokercli setup
```

Walks you through configuring all seats and table settings up front, without starting a game. Saves everything to `.env`. Use this if you want to configure all seats before playing.

```bash
# Jump straight to 4 seats
python -m pokercli setup --seats 4 --stack-bb 150 --max-hands 30
```

### `simulate` — Batch Backtesting

```bash
python -m pokercli simulate --hands 1000 --seed 42
```

Runs a batch simulation without human interaction. All seats are controlled by controllers (LLM or rule-based).

#### Default (all rule bots):

Without a lineup file, it creates 6 rule-based bots. **No API keys needed, no LLM costs.**

```bash
python -m pokercli simulate --hands 5000 --seed 1 --csv-out results.csv
```

#### With a lineup file:

```bash
python -m pokercli simulate --lineup lineup.json --json-out summary.json
```

**Lineup file format (`lineup.json`):**

```json
[
  {"type": "rule", "name": "TightBot"},
  {"type": "llm", "env_seat": 2, "name": "GPT-4o"},
  {"type": "llm", "env_seat": 3, "name": "Claude"},
  {"type": "rule", "name": "LooseBot"},
  {"type": "rule", "name": "RandomBot"},
  {"type": "rule", "name": "AggroBot"}
]
```

**How `env_seat` works:**
- LLM lineup entries reference seat blocks in your `.env` file by number.
- The simulation reuses provider, model, base URL, timeout, and API key from the `.env` seat block.
- Temperature is **forced to 0** (deterministic) for reproducibility.
- Rule bots don't need `.env` entries.

#### Options:

```bash
# Number of hands (default 1000)
python -m pokercli simulate --hands 10000

# Random seed for reproducibility
python -m pokercli simulate --seed 42

# Export results
python -m pokercli simulate --csv-out results.csv
python -m pokercli simulate --json-out summary.json
python -m pokercli simulate --csv-out results.csv --json-out summary.json

# With LLM debug logging
python -m pokercli simulate --debug-llm-log --lineup lineup.json
```

### `replay` — Replay Stored Hands

Every hand played in a live session is stored in the SQLite database. Replay them:

```bash
# Replay the latest hand from a session
python -m pokercli replay --session-id 582354f1-502a-46df-857d-da23626278f8

# Replay a specific hand by its ID
python -m pokercli replay --hand-id <hand-uuid>
```

Replay is a **re-render** of stored hand history (not a re-execution), so it's instant and requires no API calls.

---

## Analytics & Metrics

PokerCLI computes per-seat analytics after every session. Here's what each metric means:

| Metric | Full Name | Description |
|---|---|---|
| **PnL** | Profit and Loss | Net chips won/lost across all hands |
| **BB/100** | Big Blinds per 100 Hands | Standardized win rate |
| **VPIP** | Voluntarily Put Money In Pot | % of hands the player voluntarily entered the pot |
| **PFR** | Pre-Flop Raise | % of hands the player raised pre-flop |
| **3B** | 3-Bet Rate | % of opportunities where the player 3-bet |
| **SD Win** | Showdown Win Rate | % of showdowns the player won |
| **Max DD** | Maximum Drawdown | Largest peak-to-trough decline in chips |
| **Vol** | Volatility | Standard deviation of per-hand results (in BB) |
| **RoR** | Risk of Ruin | Estimated probability of losing the entire bankroll |

**Example session summary:**
```
┌──────┬──────────────────┬───────┬─────────┬────────┬────────┬──────┬────────┬─────────┬──────┬──────┐
│ Seat │ Player           │ PnL   │ BB/100  │ VPIP   │ PFR    │ 3B   │ SD Win │ Max DD  │ Vol  │ RoR  │
├──────┼──────────────────┼───────┼─────────┼────────┼────────┼──────┼────────┼─────────┼──────┼──────┤
│ 0    │ You              │ -100  │ -33.33  │ 66.67% │ 33.33% │ 0.0% │ 0.00%  │ 250     │ 1.55 │ 100% │
│ 1    │ deepseek openrtr │ 100   │ 33.33   │ 0.00%  │ 0.00%  │ 0.0% │ 0.00%  │ 150     │ 1.55 │ 0.0% │
└──────┴──────────────────┴───────┴─────────┴────────┴────────┴──────┴────────┴─────────┴──────┴──────┘
```

### Export Formats

**JSON:**
```json
{
  "hands": 1000,
  "seats": {
    "0": {
      "seat": 0,
      "player_name": "RuleBot",
      "hands": 1000,
      "pnl": 15200,
      "bb_per_100": 15.2,
      "vpip": 0.234,
      "pfr": 0.118,
      "three_bet_rate": 0.045,
      "showdown_win_rate": 0.612,
      "max_drawdown": 3400,
      "volatility": 8.72,
      "risk_of_ruin": 0.0023
    }
  }
}
```

**CSV:**
```csv
seat,player_name,hands,pnl,bb_per_100,vpip,pfr,three_bet_rate,showdown_win_rate,max_drawdown,volatility,risk_of_ruin
0,RuleBot,1000,15200,15.2,0.234,0.118,0.045,0.612,3400,8.72,0.0023
```

---

## LLM Debug Logs

When enabled (via `--debug-llm-log` or `POKER_DEBUG_LLM=1`), PokerCLI writes per-session JSON logs to `llm_debug/<session_id>.json`.

Each log file contains:
- Session metadata (session ID, mode, config)
- A `calls` array with one entry per LLM provider call

**Each call entry includes:**
- Request kind (`initial` or `retry`)
- Provider and model
- Success/failure status
- Outcome (`accepted`, `illegal_action`, `invalid_json`, `provider_error`)
- Latency in milliseconds
- Normalized turn request (system prompt, user prompt, response schema)
- Normalized turn response (content returned by the LLM)
- Raw provider request (URL, headers sans auth, body)
- Raw provider response (status code, body)
- Error text (if failed)

> **Secrets are safe:** API keys and auth headers are **never** written to debug logs.

Enable globally (all sessions):
```bash
set POKER_DEBUG_LLM=1     # Windows
export POKER_DEBUG_LLM=1   # macOS/Linux
```

Enable per-session (overrides the env var):
```bash
python -m pokercli play --debug-llm-log
python -m pokercli simulate --debug-llm-log --lineup lineup.json
```

The `llm_debug/` directory is **gitignored**.

---

## Architecture

```
cli.py (Typer commands)
  ├── play   → interactive live session
  ├── setup  → write .env interactively
  ├── simulate → batch backtest
  └── replay → re-render stored hands
      │
      ▼
engine/game.py (PokerGame — hand lifecycle state machine)
  ├── setup → preflop → flop → turn → river → showdown → settlement → complete
  ├── Side pot support for multi-way short all-ins
  ├── Bankroll ledger and buy-in/payout tracking
  └── Seeded RNG (engine/rng.py) for reproducible simulations
      │
      ▼
agents/controllers.py (SeatController protocol)
  ├── HumanController → interactive terminal input
  ├── LLMController → LLM API with retry, fallback, and status callbacks
  └── RuleBotController → deterministic rule-based bot
      │
      ▼
llm/providers.py (ProviderAdapter pattern)
  ├── OpenAIProvider → api.openai.com
  ├── AnthropicProvider → api.anthropic.com
  ├── OpenRouterProvider → openrouter.ai
  ├── NVIDIAProvider → integrate.api.nvidia.com
  └── OpenAICompatibleProvider → any /chat/completions endpoint
      │
      ▼
engine/models.py (shared data classes)
  ├── SeatView → per-seat information (hole cards + public state only)
  ├── HandHistory → full hand record
  ├── ActionDecision → parsed action from any controller
  └── RefereeState → internal game state
      │
      ▼
store.py (SQLite: sessions, hands, actions, LLM logs)
analytics.py (VPIP, PFR, PnL, 3-bet rate, etc. from stored data)
render.py (Rich-based terminal UI)
config.py (app config via platformdirs)
live_env.py (.env parsing and validation)
debug_logs.py (per-session JSON LLM debug logger)
```

**Key Design Decisions:**

- **Information segmentation:** `SeatView` is constructed per seat so each controller only sees its own hole cards plus public board state. Verified by `test_redaction.py`.
- **Provider adapter pattern:** All LLM providers implement `ProviderAdapter.complete_turn()`, normalizing request/response handling.
- **Session memory:** `LLMController` maintains per-seat message history (default 5 hands) so the model has context across hands.
- **Hand lifecycle state machine:** `PokerGame` drives a strict street-by-street state machine with side pot support.
- **SQLite storage:** Every action and LLM call is persisted. Replay is re-render, not re-execution.

---

## Troubleshooting

### "Python was not found on PATH" (Windows)

**Solution:** Python isn't in your PATH.
1. Reinstall Python from [python.org](https://www.python.org/downloads/)
2. **Check** "Add Python to PATH" during installation
3. Open a **new** terminal window and try again

### "Python version must be 3.13 or higher"

**Solution:** You have an older Python installed.
- **Windows:** Install Python 3.13 from python.org (it can coexist with older versions). Use `py -3.13 -m pokercli play`.
- **macOS:** `brew install python@3.13` then use `python3.13`.
- **Linux:** Use deadsnakes PPA or pyenv to get 3.13.

### "Seat X is incomplete" during `play`

**Solution:** The `.env` is missing some fields for that seat. Run `python -m pokercli setup` to reconfigure all seats, or just run `play` again — it will prompt for missing seats.

### LLM returns "Provider returned empty/null content"

**Cause:** The model refused to respond or returned a tool call instead of text.

**Solution:**
- Try a different model. Some small models struggle with the JSON format.
- Make sure the model supports JSON mode (`response_format: json_object`).
- OpenAI `gpt-4o`/`gpt-4o-mini` and Claude Sonnet work reliably.
- Rule bots are always a fallback — no API needed.

### LLM keeps returning illegal actions

**Cause:** The model doesn't understand poker rules or the response format.

**Solution:**
- Use a more capable model (GPT-4o, Claude Sonnet, etc.)
- Set temperature to `0` for deterministic output
- If it persists, the LLM seat will fall back to the rule-based bot after 2 failures

### Rate limits / "429 Too Many Requests"

**Cause:** You're hitting the API too fast (common with free tiers).

**Solution:**
- Increase timeout (`POKER_SEAT_N_TIMEOUT_S`)
- Use fewer LLM seats
- Add more rule bots to your lineup (they're free)
- Upgrade your API plan

### SQLite "database is locked"

**Cause:** Another pokercli process is running, or the database file is on a network drive.

**Solution:**
- Close other pokercli processes
- Move the database to a local drive (set `database_path` in `config.json`)

### No such command: `simulate` / `play` / `replay`

**Cause:** The package isn't installed correctly.

**Solution:**
```bash
pip install -e ".[dev]"  # reinstall from the repo root
python -m pokercli --help  # verify
```

---

## Development

### Setup

```bash
pip install -e ".[dev]"
```

### Run Tests

```bash
# All tests
python -m pytest -q

# Specific test file
python -m pytest tests/test_game_rules.py -q

# With verbose output
python -m pytest -v

# Run redaction tests (verifies information segmentation)
python -m pytest tests/test_redaction.py -v
```

### Project Structure

```
pokercli/
├── pokercli/           # Source package
│   ├── __init__.py
│   ├── __main__.py     # python -m pokercli entry point
│   ├── cli.py          # Typer commands (play, simulate, setup, replay)
│   ├── config.py       # AppConfig, platformdirs paths
│   ├── debug_logs.py   # SessionLLMDebugLogger (JSON debug logs)
│   ├── live_env.py     # .env parsing, LiveSeatConfig, validation
│   ├── analytics.py    # VPIP, PFR, PnL, drawdown, risk of ruin
│   ├── render.py       # Rich terminal UI rendering
│   ├── store.py        # SQLite session/hand/action/LLM log storage
│   ├── agents/
│   │   ├── __init__.py
│   │   └── controllers.py  # HumanController, LLMController, RuleBotController
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── game.py     # PokerGame state machine (street lifecycle)
│   │   ├── models.py   # Data classes (SeatView, HandHistory, etc.)
│   │   ├── cards.py    # Card, Deck, suit/rank primitives
│   │   ├── evaluator.py # Poker hand evaluator (rank categories)
│   │   └── rng.py      # Seeded RNG provider
│   └── llm/
│       ├── __init__.py
│       └── providers.py  # ProviderAdapter, 5 provider implementations
├── tests/              # Test suite
│   ├── conftest.py
│   ├── test_game_rules.py
│   ├── test_controllers.py
│   ├── test_evaluator.py
│   ├── test_llm_controller.py
│   ├── test_redaction.py  # Information segmentation contract tests
│   ├── test_render.py
│   ├── test_rng.py
│   └── test_cli.py
├── pyproject.toml      # Package metadata, dependencies, build config
├── requirements.txt    # Pip-compatible dependency list
├── .env.example        # Template (safe to share, no real keys)
├── .gitignore
├── play_poker.bat      # Windows convenience launcher
├── CLAUDE.md           # Claude Code guidance
└── README.md           # You are here
```

---

## License

MIT — see [LICENSE](LICENSE) for details.

---

<div align="center">

**Made with ♠️ ♥️ ♦️ ♣️ and LLMs**

*"Fold pre." — Every poker bot ever*

</div>
