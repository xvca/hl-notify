import asyncio
import logging
import re

from telegram import Update
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
    short_addr,
)
from ws_manager import WSManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

ETH_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")

ws_manager: WSManager | None = None
app: Application | None = None


def auth(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != TELEGRAM_USER_ID:
            return
        return await func(update, context)
    return wrapper


async def send_notification(wallet: str, event_type: str, data: dict):
    if not storage.is_event_enabled(wallet, event_type):
        return

    formatters = {
        "fills": format_fill,
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
        "/watch <address> — Add wallet\n"
        "/unwatch <address> — Remove wallet\n"
        "/list — Show watched wallets\n"
        "/events <address> — Toggle event types\n"
        "/status — Connection status"
    )


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
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wallet_count = len(storage.get_wallets())
    connected = ws_manager.connected if ws_manager else False
    status = "🟢 Connected" if connected else "🔴 Disconnected"
    await update.message.reply_text(
        f"WebSocket: {status}\nWallets: {wallet_count}"
    )


async def post_init(application: Application):
    global ws_manager
    ws_manager = WSManager(on_event=send_notification)
    await ws_manager.start()

    wallet_count = len(storage.get_wallets())
    await application.bot.send_message(
        chat_id=TELEGRAM_USER_ID,
        text=f"🟢 Bot online\nWatching {wallet_count} wallet(s)",
    )


async def post_shutdown(application: Application):
    if ws_manager:
        await ws_manager.stop()


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
    app.add_handler(CommandHandler("watch", cmd_watch))
    app.add_handler(CommandHandler("unwatch", cmd_unwatch))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("events", cmd_events))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CallbackQueryHandler(handle_toggle))

    logger.info("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
