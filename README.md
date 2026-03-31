# Squirdle Bot

A Discord bot that brings the Wordle-style guessing experience to Pokémon. Try to identify the secret Pokémon in 9 tries using hints about its generation, type, height, weight, and Pokédex number.

Supports two independent game modes — a shared daily puzzle and a private personal game — running simultaneously per user.

---

## Features

- **Daily mode** — everyone guesses the same Pokémon each day, seeded by UTC date
- **Personal mode** — private game, only visible to you, can be quit at any time
- **Hint system** — 5 attributes compared per guess (generation, type, height, weight, Pokédex number)
- **Public leaderboard** — ranked by attempts then completion time; your Pokémon stays private
- **Autocomplete** — Pokémon name suggestions as you type
- **Privacy-first** — most commands use ephemeral messages (only you see the response)
- **Heroku-ready** — Flask keep-alive server included for persistent deployment

---

## Commands

| Command | Visibility | Description |
|---------|------------|-------------|
| `/start` | Private | Start a new personal Squirdle game |
| `/daily` | Public | Begin or resume today's shared daily puzzle |
| `/guess name:<pokemon>` | Private | Make a guess in your active game(s) |
| `/stats` | Private | View your daily and personal stats with last guess breakdown |
| `/status` | Private | Check current progress for both game modes |
| `/leaderboard` | Mixed | Top 10 solvers publicly; your rank and Pokémon privately |
| `/quit` | Private | End your personal game and reveal the Pokémon |
| `/help` | Private | Show the in-game guide |
| `!sync` | Owner only | Manually sync slash commands with Discord |

---

## How to Play

1. Use `/start` for a personal game or `/daily` to join today's shared puzzle.
2. Use `/guess` to guess a Pokémon by name (autocomplete supported).
3. Each guess returns hints for 5 attributes:

| Attribute | Hint |
|-----------|------|
| **Generation** | Earlier / Later / Same |
| **Type** | Shared types listed, or "none" |
| **Height** | Taller / Shorter / Same |
| **Weight** | Heavier / Lighter / Same |
| **Pokédex Number** | Higher / Lower / Same |

4. You have **9 tries**. Run out and the Pokémon is revealed privately.
5. You can play both modes at the same time — progress is tracked separately.

---

## Project Structure

```
squirdle-bot/
├── src/
│   ├── bot.py              # Discord bot — all commands, game state, embeds
│   ├── game_logic.py       # Core game mechanics, hint generation, CLI test mode
│   └── fetch_pokemon.py    # Fetches and caches Pokémon data from PokeAPI
├── data/
│   └── pokemon.json        # Cached Pokémon database (~1000 entries)
├── requirements.txt
├── runtime.txt             # Python 3.11.9 (for Heroku)
├── Procfile                # Heroku entry point
└── .env                    # DISCORD_TOKEN (not committed)
```

---

## Setup

### Prerequisites

- Python 3.11+
- A Discord bot token ([Discord Developer Portal](https://discord.com/developers/applications))

### Installation

```bash
git clone https://github.com/OWaseem/squirdle-discord-bot.git
cd squirdle-discord-bot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Configuration

Create a `.env` file in the root:

```
DISCORD_TOKEN=your_token_here
```

### Run

```bash
python -m src.bot
```

### Refresh Pokémon Data (optional)

To re-fetch the Pokémon database from PokeAPI:

```bash
python -m src.fetch_pokemon
```

This regenerates `data/pokemon.json`.

---

## Deployment (Heroku)

The bot includes a Flask keep-alive server that responds to HTTP pings, preventing Heroku's free-tier dynos from sleeping.

1. Push the repo to Heroku.
2. Set the `DISCORD_TOKEN` config var in the Heroku dashboard.
3. The `Procfile` (`web: python -m src.bot`) handles the rest.

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `discord.py==2.4.0` | Discord bot framework and slash commands |
| `httpx==0.27.2` | Async HTTP client for PokeAPI requests |
| `tqdm==4.66.5` | Progress bar for data fetching |
| `python-dotenv==1.0.1` | `.env` file loading |
| `Flask==3.0.0` | Keep-alive web server |
| `audioop-lts` | Legacy audio compatibility |
