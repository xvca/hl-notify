import asyncio
from datetime import datetime, timezone
import hashlib
import logging
from pathlib import Path
import re

from telegram import BotCommand, Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_USER_ID
import storage
from formatter import (
    format_fill,
    format_liquidation,
    format_funding,
    format_transfer,
    format_aggregated_fills,
    format_positions,
    short_addr,
)
from ws_manager import WSManager
from aggregator import FillAggregator
from hyperliquid_api import (
    close_http_session,
    get_position_info,
    get_positions_report,
    http_session_ready,
    init_http_session,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

ETH_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")

ws_manager: WSManager | None = None
fill_aggregator: FillAggregator | None = None
app: Application | None = None
STARTED_AT = datetime.now(timezone.utc)


def compute_build_id() -> str:
    root = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    files = sorted(root.glob("*.py"))
    extras = [root / "pyproject.toml", root / "uv.lock"]

    try:
        for path in [*files, *extras]:
            if not path.exists():
                continue
            digest.update(path.name.encode("utf-8"))
            digest.update(path.read_bytes())
    except OSError:
        return "unknown"

    return digest.hexdigest()[:8]


APP_BUILD_ID = compute_build_id()
BOT_COMMANDS = [
    BotCommand("help", "Show available commands"),
    BotCommand("watch", "Add a wallet to monitor"),
    BotCommand("unwatch", "Remove a wallet"),
    BotCommand("list", "Show watched wallets"),
    BotCommand("events", "Toggle event types for a wallet"),
    BotCommand("positions", "Show open positions and PnL"),
    BotCommand("status", "Show WebSocket status and build info"),
]


def format_command_help() -> str:
    return "\n".join(
        f"/{command.command} - {command.description}"
        for command in BOT_COMMANDS
    )


def format_uptime() -> str:
    elapsed = int((datetime.now(timezone.utc) - STARTED_AT).total_seconds())
    hours, remainder = divmod(elapsed, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def auth(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != TELEGRAM_USER_ID:
            return
        return await func(update, context)
    return wrapper


async def send_aggregated_fills(wallet: str, fills: list[dict]):
    if not storage.is_event_enabled(wallet, "fills"):
        return

    if not fills:
        return

    first = fills[0]
    coin = first.get("coin", "")
    direction = first.get("dir", "")

    position_info = None
    if direction in ("Open Long", "Open Short"):
        position_info = await get_position_info(wallet, coin)

    text = format_aggregated_fills(fills, wallet, position_info)
    try:
        await app.bot.send_message(
            chat_id=TELEGRAM_USER_ID,
            text=f"```\n{text}\n```",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Failed to send aggregated fill notification: {e}")


async def send_notification(wallet: str, event_type: str, data: dict):
    if not storage.is_event_enabled(wallet, event_type):
        return

    formatters = {
        "liquidations": format_liquidation,
        "funding": format_funding,
        "transfers": format_transfer,
    }
    fmt = formatters.get(event_type)
    if not fmt:
        return

    text = fmt(data, wallet)
    try:
        await app.bot.send_message(
            chat_id=TELEGRAM_USER_ID,
            text=f"```\n{text}\n```",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Failed to send notification: {e}")


@auth
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hyperliquid Notify Bot\n\n"
        "Commands:\n"
        f"{format_command_help()}\n\n"
        "Use /watch <address> and /events <address> with a wallet address."
    )


@auth
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_start(update, context)


@auth
async def cmd_watch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not ETH_ADDRESS_RE.match(context.args[0]):
        await update.message.reply_text("Usage: /watch <0x address>")
        return

    address = context.args[0].lower()
    if storage.add_wallet(address):
        await ws_manager.subscribe(address)
        await update.message.reply_text(f"Watching {short_addr(address)}")
    else:
        await update.message.reply_text(f"Already watching {short_addr(address)}")


@auth
async def cmd_unwatch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not ETH_ADDRESS_RE.match(context.args[0]):
        await update.message.reply_text("Usage: /unwatch <0x address>")
        return

    address = context.args[0].lower()
    if storage.remove_wallet(address):
        await ws_manager.unsubscribe(address)
        await update.message.reply_text(f"Unwatched {short_addr(address)}")
    else:
        await update.message.reply_text("Wallet not found")


@auth
async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wallets = storage.get_wallets()
    if not wallets:
        await update.message.reply_text("No wallets being watched")
        return

    lines = []
    for addr, info in wallets.items():
        enabled = [k for k, v in info["events"].items() if v]
        lines.append(f"• {short_addr(addr)}  [{', '.join(enabled)}]")
    await update.message.reply_text("\n".join(lines))


@auth
async def cmd_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not ETH_ADDRESS_RE.match(context.args[0]):
        await update.message.reply_text("Usage: /events <0x address>")
        return

    address = context.args[0].lower()
    events = storage.get_events(address)
    if events is None:
        await update.message.reply_text("Wallet not found. /watch it first.")
        return

    buttons = []
    for event_type, enabled in events.items():
        icon = "✅" if enabled else "❌"
        buttons.append([
            InlineKeyboardButton(
                f"{icon} {event_type}",
                callback_data=f"toggle:{address}:{event_type}",
            )
        ])
    await update.message.reply_text(
        f"Event toggles for {short_addr(address)}:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


@auth
async def handle_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    if len(parts) != 3 or parts[0] != "toggle":
        return

    address, event_type = parts[1], parts[2]
    new_state = storage.toggle_event(address, event_type)
    if new_state is None:
        return

    events = storage.get_events(address)
    buttons = []
    for et, enabled in events.items():
        icon = "✅" if enabled else "❌"
        buttons.append([
            InlineKeyboardButton(
                f"{icon} {et}",
                callback_data=f"toggle:{address}:{et}",
            )
        ])
    await query.edit_message_reply_markup(
        reply_markup=InlineKeyboardMarkup(buttons)
    )


@auth
async def cmd_positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and ETH_ADDRESS_RE.match(context.args[0]):
        address = context.args[0].lower()
        if address not in storage.get_wallets():
            await update.message.reply_text("Wallet not found. /watch it first.")
            return
        wallets_to_check = [address]
    else:
        wallets_to_check = list(storage.get_wallets().keys())

    if not wallets_to_check:
        await update.message.reply_text("No wallets being watched. /watch one first.")
        return

    await update.message.reply_text("Fetching positions...")

    for wallet in wallets_to_check:
        report = await get_positions_report(wallet)
        text = format_positions(report["positions"], wallet, report)
        await update.message.reply_text(f"```\n{text}\n```", parse_mode="Markdown")


@auth
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wallet_count = len(storage.get_wallets())
    connected = ws_manager.connected if ws_manager else False
    status = "🟢 Connected" if connected else "🔴 Disconnected"
    http_status = "🟢 Ready" if http_session_ready() else "🟡 Lazy"
    await update.message.reply_text(
        f"WebSocket: {status}\n"
        f"HTTP: {http_status}\n"
        f"Wallets: {wallet_count}\n"
        f"Build: {APP_BUILD_ID}\n"
        f"Uptime: {format_uptime()}"
    )


async def post_init(application: Application):
    global ws_manager, fill_aggregator
    await init_http_session()
    await application.bot.set_my_commands(BOT_COMMANDS)
    fill_aggregator = FillAggregator(on_batch=send_aggregated_fills)
    ws_manager = WSManager(
        on_event=send_notification,
        on_fill=fill_aggregator.add_fill,
    )
    await ws_manager.start()

    wallet_count = len(storage.get_wallets())
    await application.bot.send_message(
        chat_id=TELEGRAM_USER_ID,
        text=f"🟢 Bot online\nWatching {wallet_count} wallet(s)",
    )


async def post_shutdown(application: Application):
    if ws_manager:
        await ws_manager.stop()
    await close_http_session()


def main():
    global app
    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("watch", cmd_watch))
    app.add_handler(CommandHandler("unwatch", cmd_unwatch))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("events", cmd_events))
    app.add_handler(CommandHandler("positions", cmd_positions))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CallbackQueryHandler(handle_toggle))

    logger.info("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
