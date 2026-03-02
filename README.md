# hl-notify

A single-user Telegram bot that watches Hyperliquid L1 wallets over WebSocket and sends you notifications when things happen: fills, liquidations, funding payments, and deposits or withdrawals.

You can monitor as many wallets as you want. Add them with `/watch`, configure notification preferences per wallet, and the bot handles all the subscriptions over one WebSocket connection.

## How it works

The bot opens one WebSocket connection to `wss://api.hyperliquid.xyz/ws` and subscribes to events for each wallet you add. When something comes in, it checks your per-wallet event preferences, formats the message, and sends it to your Telegram.

If the connection drops, it reconnects with exponential backoff and resubscribes to everything automatically.

## Setup

### 1. Create a Telegram bot

Talk to [@BotFather](https://t.me/BotFather) on Telegram, create a bot, grab the token.

You also need your Telegram user ID. Send a message to [@userinfobot](https://t.me/userinfobot) to get it.

The bot sets its Telegram command menu automatically when it starts, so commands should appear as soon as you type `/` in chat.

### 2. Configure

```sh
cp .env.example .env
```

Edit `.env`:

```
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_USER_ID=987654321
```

### 3a. Run with Docker

Build and start the bot:

```sh
docker compose up --build -d
```

Wallet config persists in `./data/config.json` via a volume mount.

If you update the code, rebuild so the running container picks up the latest changes:

```sh
docker compose up --build -d
```

### 3b. Run without Docker

Using `uv` (recommended):

```sh
uv sync
uv run bot.py
```

If you want `uv` to manage the Python version too:

```sh
uv python install 3.12
uv sync
uv run bot.py
```

If you update the code locally, restart the bot with `uv run bot.py`.

## Commands

`/start` - usage info

`/help` - show available commands

`/watch <addr>` - start watching a wallet

`/unwatch <addr>` - stop watching a wallet

`/list` - show all watched wallets and their enabled events

`/events <addr>` - toggle which event types you get notified about

`/positions [addr]` - show open positions, current price, leverage, margin, unrealized PnL, and funding since open. If no address is provided, the bot checks every watched wallet. This also includes HIP-3 positions.

`/status` - show WebSocket status, HTTP session status, build ID, uptime, and wallet count

## Event types

Each wallet has four event types you can toggle independently with `/events`:

- **fills**: trade executions (buy or sell, price, size, direction, PnL on close)
- **liquidations**: liquidation events
- **funding**: hourly funding rate payments
- **transfers**: deposits, withdrawals, and internal transfers

All four are on by default when you add a wallet.

## Notes

- The bot reuses one shared HTTP session for Hyperliquid API calls instead of opening a new connection for every request.
- If `/positions` comes back empty, the response now includes a little more context, including partial API failures and a hint when an agent or signer wallet may be the issue.
- Telegram command suggestions are synced automatically on startup, so you usually do not need to manage them manually in BotFather.

## Project structure

`bot.py` - entry point and Telegram command handlers

`ws_manager.py` - WebSocket connection, subscriptions, and reconnect logic

`hyperliquid_api.py` - Hyperliquid REST helpers and position lookups

`formatter.py` - turns raw events into readable messages

`storage.py` - JSON persistence for wallet list and event preferences

`config.py` - environment variable loading

`tests/` - focused tests for formatting and Hyperliquid API parsing

## Dependencies

This project uses `uv` with [pyproject.toml](/Users/lv/Developer/Repos/Projects/hl-notify/pyproject.toml) for dependency management.

## Testing

```sh
uv sync --group dev
uv run --group dev pytest
```

## Security

The bot only responds to the Telegram user ID in your `.env`. Messages from anyone else are silently ignored.
