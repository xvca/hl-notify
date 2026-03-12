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
    BotCommand("label", "Set or clear a wallet label"),
    BotCommand("unwatch", "Remove a wallet"),
    BotCommand("list", "Show watched wallets"),
    BotCommand("events", "Toggle event types for a wallet"),
    BotCommand("fundingfilter", "View or update funding alert thresholds"),
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


def format_wallet_name(address: str) -> str:
    label = storage.get_label(address)
    if label:
        return f"{label} ({short_addr(address)})"
    return short_addr(address)


def resolve_wallet_ref(ref: str) -> str | None:
    if ETH_ADDRESS_RE.match(ref):
        return ref.lower()
    return storage.find_wallet_by_label(ref)


def parse_optional_threshold(raw: str) -> float | None:
    if raw.lower() == "off":
        return None

    value = float(raw)
    if value < 0:
        raise ValueError("Thresholds must be non-negative")
    return value


def format_threshold(value: float | None, suffix: str = "") -> str:
    if value is None:
        return "off"
    if suffix:
        return f"{value:g}{suffix}"
    return f"{value:g}"


def format_funding_rule(filters: dict) -> str:
    annualized_threshold = filters.get("annualized_threshold")
    usdc_threshold = filters.get("usdc_threshold")

    if annualized_threshold is None and usdc_threshold is None:
        return "notify on every funding event"

    if annualized_threshold is None:
        return f"notify only when payment is at least ${usdc_threshold:g}"

    if usdc_threshold is None:
        return (
            "notify only when annualized funding is at least "
            f"{annualized_threshold:g}%"
        )

    return (
        "notify when annualized funding is at least "
        f"{annualized_threshold:g}% or payment is at least ${usdc_threshold:g}"
    )


def should_send_funding_notification(wallet: str, funding: dict) -> bool:
    filters = storage.get_funding_filters(wallet)
    if not filters:
        return False

    annualized_threshold = filters.get("annualized_threshold")
    usdc_threshold = filters.get("usdc_threshold")

    if annualized_threshold is None and usdc_threshold is None:
        return True

    triggered = False

    if usdc_threshold is not None:
        try:
            triggered = abs(float(funding.get("usdc", 0))) >= float(usdc_threshold)
        except (ValueError, TypeError):
            pass

    if annualized_threshold is not None:
        try:
            annualized = abs(float(funding.get("fundingRate", 0))) * 24 * 365 * 100
            triggered = triggered or annualized >= float(annualized_threshold)
        except (ValueError, TypeError):
            pass

    return triggered


def format_funding_config(address: str, filters: dict) -> str:
    annualized = format_threshold(filters.get("annualized_threshold"), "%")
    usdc = format_threshold(filters.get("usdc_threshold"))
    if usdc != "off":
        usdc = f"${usdc}"
    display_name = format_wallet_name(address)

    return (
        f"Funding alerts for {display_name}\n"
        f"Annualized threshold: {annualized}\n"
        f"USD threshold: {usdc}\n"
        f"Rule: {format_funding_rule(filters)}\n"
        f"Usage: /fundingfilter {address} <annualized_pct|off> <usd|off>\n"
        f"Example: /fundingfilter {address} off 5"
    )


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
            text=text,
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Failed to send aggregated fill notification: {e}")


async def send_notification(wallet: str, event_type: str, data: dict):
    if not storage.is_event_enabled(wallet, event_type):
        return
    if event_type == "funding" and not should_send_funding_notification(wallet, data):
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
            text=text,
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Failed to send notification: {e}")


@auth
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hyperliquid Notify Bot\n\n"
        "Commands:\n"
        f"{format_command_help()}\n\n"
        "Use /watch <address> [label] to add wallets, and you can use either an address or a label with /label, /events, /fundingfilter, /positions, and /unwatch."
    )


@auth
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_start(update, context)


@auth
async def cmd_watch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not ETH_ADDRESS_RE.match(context.args[0]):
        await update.message.reply_text("Usage: /watch <0x address> [label]")
        return

    address = context.args[0].lower()
    label = " ".join(context.args[1:]).strip() or None

    if storage.add_wallet(address, label=label):
        await ws_manager.subscribe(address)
        await update.message.reply_text(f"Watching {format_wallet_name(address)}")
    else:
        await update.message.reply_text(
            f"Already watching {format_wallet_name(address)} or that label is already in use."
        )


@auth
async def cmd_label(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /label <address|label> <new label|clear>")
        return

    address = resolve_wallet_ref(context.args[0])
    if not address:
        await update.message.reply_text("Wallet not found. /watch it first.")
        return

    if len(context.args) == 1:
        current = storage.get_label(address)
        current_text = current if current else "none"
        await update.message.reply_text(
            f"Label for {short_addr(address)}: {current_text}\n"
            "Usage: /label <address|label> <new label|clear>"
        )
        return

    raw_label = " ".join(context.args[1:]).strip()
    new_label = None if raw_label.lower() == "clear" else raw_label
    result = storage.set_label(address, new_label)
    if result is False:
        await update.message.reply_text("That label is already in use.")
        return

    if result is None:
        await update.message.reply_text("Wallet not found. /watch it first.")
        return

    if result:
        await update.message.reply_text(
            f"Updated label for {short_addr(address)} to {result}"
        )
    else:
        await update.message.reply_text(
            f"Cleared label for {short_addr(address)}"
        )


@auth
async def cmd_unwatch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /unwatch <address|label>")
        return

    address = resolve_wallet_ref(context.args[0])
    if not address:
        await update.message.reply_text("Wallet not found")
        return

    if storage.remove_wallet(address):
        await ws_manager.unsubscribe(address)
        await update.message.reply_text(f"Unwatched {format_wallet_name(address)}")
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
        wallet_name = info.get("label") or short_addr(addr)
        if info.get("label"):
            wallet_name = f"{wallet_name} ({short_addr(addr)})"
        lines.append(f"• {wallet_name}  [{', '.join(enabled)}]")
    await update.message.reply_text("\n".join(lines))


@auth
async def cmd_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /events <address|label>")
        return

    address = resolve_wallet_ref(context.args[0])
    if not address:
        await update.message.reply_text("Wallet not found. /watch it first.")
        return

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
        f"Event toggles for {format_wallet_name(address)}:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


@auth
async def cmd_fundingfilter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Usage: /fundingfilter <address|label> [<annualized_pct|off> <usd|off>]"
        )
        return

    address = resolve_wallet_ref(context.args[0])
    if not address:
        await update.message.reply_text("Wallet not found. /watch it first.")
        return

    if len(context.args) == 1:
        filters = storage.get_funding_filters(address)
        await update.message.reply_text(format_funding_config(address, filters))
        return

    if len(context.args) != 3:
        await update.message.reply_text(
            "Usage: /fundingfilter <address|label> [<annualized_pct|off> <usd|off>]"
        )
        return

    try:
        annualized_threshold = parse_optional_threshold(context.args[1])
        usdc_threshold = parse_optional_threshold(context.args[2])
    except ValueError:
        await update.message.reply_text(
            "Thresholds must be non-negative numbers or 'off'."
        )
        return

    filters = storage.set_funding_filters(
        address,
        annualized_threshold=annualized_threshold,
        usdc_threshold=usdc_threshold,
    )
    await update.message.reply_text(
        "Updated funding alert settings.\n\n"
        f"{format_funding_config(address, filters)}"
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
    if context.args:
        address = resolve_wallet_ref(context.args[0])
        if not address:
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
        await update.message.reply_text(text, parse_mode="HTML")


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
    app.add_handler(CommandHandler("label", cmd_label))
    app.add_handler(CommandHandler("unwatch", cmd_unwatch))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("events", cmd_events))
    app.add_handler(CommandHandler("fundingfilter", cmd_fundingfilter))
    app.add_handler(CommandHandler("positions", cmd_positions))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CallbackQueryHandler(handle_toggle))

    logger.info("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
