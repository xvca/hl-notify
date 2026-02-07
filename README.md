# hl-notify

A single-user Telegram bot that watches Hyperliquid L1 wallets over WebSocket and sends you notifications when things happen -- fills, liquidations, funding payments, deposits/withdrawals.

You can monitor as many wallets as you want. Add them with `/watch`, configure notification preferences per wallet, and the bot handles all the subscriptions over one WebSocket connection.

## How it works

The bot opens one WebSocket connection to `wss://api.hyperliquid.xyz/ws` and subscribes to events for each wallet you add. When something comes in, it checks your per-wallet event preferences, formats the message, and sends it to your Telegram.

If the connection drops, it reconnects with exponential backoff and resubscribes to everything automatically.

## Setup

### 1. Create a Telegram bot

Talk to [@BotFather](https://t.me/BotFather) on Telegram, create a bot, grab the token.

You also need your Telegram user ID. Send a message to [@userinfobot](https://t.me/userinfobot) to get it.

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

```sh
docker compose up --build -d
```

Wallet config persists in `./data/config.json` via a volume mount.

### 3b. Run without Docker

Using pyenv (recommended):

```sh
# Install pyenv if you don't have it
# macOS: brew install pyenv
# Linux: curl https://pyenv.run | bash

pyenv install 3.12
pyenv local 3.12
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python bot.py
```

Or without pyenv:

```sh
pip install -r requirements.txt
python bot.py
```

## Commands

```
/start          -- usage info
/watch <addr>   -- start watching a wallet
/unwatch <addr> -- stop watching a wallet
/list           -- show all watched wallets and their enabled events
/events <addr>  -- toggle which event types you get notified about
/status         -- WebSocket connection status and wallet count
```

## Event types

Each wallet has four event types you can toggle independently with `/events`:

- **fills** -- trade executions (buy/sell, price, size, direction, PnL on close)
- **liquidations** -- liquidation events
- **funding** -- hourly funding rate payments
- **transfers** -- deposits, withdrawals, internal transfers

All four are on by default when you add a wallet.

## Project structure

```
bot.py           -- entry point, Telegram command handlers
ws_manager.py    -- WebSocket connection, subscriptions, reconnect logic
formatter.py     -- turns raw events into readable messages
storage.py       -- JSON persistence for wallet list and event prefs
config.py        -- env var loading
```

## Security

The bot only responds to the Telegram user ID in your `.env`. Messages from anyone else are silently ignored.
