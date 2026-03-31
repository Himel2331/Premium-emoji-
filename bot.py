import asyncio
import json
import logging
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from dotenv import load_dotenv
from telegram import BotCommand, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("telegram-custom-emoji-id-bot")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
PORT = int(os.getenv("PORT", "10000"))
MAX_OUTPUT_IDS = int(os.getenv("MAX_OUTPUT_IDS", "500"))

HELP_TEXT = (
    "আমাকে Telegram emoji/sticker pack link দিন, আমি pack-এর ID বের করে দেব।\n\n"
    "Supported link:\n"
    "- https://t.me/addemoji/<set_name>\n"
    "- https://t.me/addstickers/<set_name>\n\n"
    "আমি যেটা বের করব:\n"
    "- custom emoji pack হলে: custom_emoji_id list\n"
    "- regular sticker pack হলে: file_unique_id list\n\n"
    "কমান্ডসমূহ:\n"
    "/start - bot শুরু\n"
    "/help - usage guide\n"
    "/commands - command list\n"
    "/ping - bot live কিনা\n"
    "/id - chat id দেখাবে\n"
    "/ids <link> - link থেকে ID বের করবে\n\n"
    "Example:\n"
    "/ids https://t.me/addemoji/prem_28a5b_by_TgEmojis_bot"
)

BOT_COMMANDS = [
    BotCommand("start", "Start the bot"),
    BotCommand("help", "Show usage guide"),
    BotCommand("commands", "Show all commands"),
    BotCommand("ping", "Check bot status"),
    BotCommand("id", "Show chat id"),
    BotCommand("ids", "Extract IDs from a Telegram pack link"),
]

ADD_LINK_RE = re.compile(
    r"(?:https?://)?(?:t(?:elegram)?\.me)/(addemoji|addstickers)/([A-Za-z0-9_]+)",
    re.IGNORECASE,
)


def chunk_text(text: str, max_length: int = 4000) -> List[str]:
    text = text or ""
    if len(text) <= max_length:
        return [text]

    chunks: List[str] = []
    current = ""
    for line in text.splitlines(True):
        if len(current) + len(line) > max_length:
            if current:
                chunks.append(current)
                current = ""
        if len(line) > max_length:
            start = 0
            while start < len(line):
                chunks.append(line[start : start + max_length])
                start += max_length
        else:
            current += line
    if current:
        chunks.append(current)
    return chunks


async def send_text_chunks(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
) -> None:
    if not update.effective_message:
        return

    safe_text = (text or "").strip() or "কোনো data পাওয়া যায়নি।"
    for chunk in chunk_text(safe_text):
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=chunk,
            reply_to_message_id=update.effective_message.message_id,
            disable_web_page_preview=True,
        )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_text_chunks(update, context, HELP_TEXT)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_text_chunks(update, context, HELP_TEXT)


async def cmd_commands(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "Available commands:\n"
        "/start - Start the bot\n"
        "/help - Show usage guide\n"
        "/commands - Show all commands\n"
        "/ping - Check bot status\n"
        "/id - Show chat id\n"
        "/ids <link> - Extract IDs from a pack link"
    )
    await send_text_chunks(update, context, text)


async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_text_chunks(update, context, "pong")


async def cmd_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id if update.effective_chat else "unknown"
    user_id = update.effective_user.id if update.effective_user else "unknown"
    await send_text_chunks(update, context, f"chat_id: {chat_id}\nuser_id: {user_id}")


def extract_pack_from_text(text: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    text = (text or "").strip()
    if not text:
        return None, None, None

    match = ADD_LINK_RE.search(text)
    if match:
        kind = match.group(1).lower()
        set_name = match.group(2)
        full_link = match.group(0)
        if not full_link.startswith("http"):
            full_link = f"https://{full_link}"
        return kind, set_name, full_link

    parsed = urlparse(text)
    if parsed.netloc.lower() in {"t.me", "telegram.me"}:
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2 and parts[0] in {"addemoji", "addstickers"}:
            return parts[0], parts[1], text

    return None, None, None


async def fetch_pack_details(
    context: ContextTypes.DEFAULT_TYPE,
    set_name: str,
) -> Tuple[str, str, int, List[str]]:
    sticker_set = await context.bot.get_sticker_set(name=set_name)
    stickers = list(sticker_set.stickers or [])
    sticker_type = getattr(sticker_set, "sticker_type", None) or "unknown"

    ids: List[str] = []
    if sticker_type == "custom_emoji":
        for sticker in stickers:
            custom_emoji_id = getattr(sticker, "custom_emoji_id", None)
            if custom_emoji_id:
                ids.append(str(custom_emoji_id))
    else:
        for sticker in stickers:
            file_unique_id = getattr(sticker, "file_unique_id", None)
            if file_unique_id:
                ids.append(str(file_unique_id))

    return sticker_set.title or set_name, sticker_type, len(stickers), ids


def build_result_text(
    pack_link: str,
    set_name: str,
    title: str,
    sticker_type: str,
    total_items: int,
    ids: List[str],
) -> str:
    limited_ids = ids[:MAX_OUTPUT_IDS]
    lines = [
        "Pack info",
        f"title: {title}",
        f"set_name: {set_name}",
        f"link: {pack_link}",
        f"type: {sticker_type}",
        f"total_items: {total_items}",
        f"total_ids_found: {len(ids)}",
        "",
    ]

    if sticker_type == "custom_emoji":
        lines.append("custom_emoji_id list:")
    else:
        lines.append("file_unique_id list:")

    if limited_ids:
        lines.extend(limited_ids)
    else:
        lines.append("No IDs found in this pack.")

    if len(ids) > len(limited_ids):
        lines.extend(
            [
                "",
                f"Note: output limited to first {len(limited_ids)} IDs. Increase MAX_OUTPUT_IDS if needed.",
            ]
        )

    if sticker_type != "custom_emoji":
        lines.extend(
            [
                "",
                "Note: এটি custom emoji pack না, তাই custom_emoji_id নেই। এর বদলে file_unique_id দেওয়া হয়েছে।",
            ]
        )

    return "\n".join(lines)


async def process_link(update: Update, context: ContextTypes.DEFAULT_TYPE, raw_text: str) -> None:
    if not update.effective_chat:
        return

    kind, set_name, pack_link = extract_pack_from_text(raw_text)
    if not set_name or not pack_link or not kind:
        await send_text_chunks(
            update,
            context,
            "Valid Telegram pack link পাইনি। Example:\nhttps://t.me/addemoji/prem_28a5b_by_TgEmojis_bot",
        )
        return

    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        title, sticker_type, total_items, ids = await fetch_pack_details(context, set_name)
        result_text = build_result_text(pack_link, set_name, title, sticker_type, total_items, ids)
        await send_text_chunks(update, context, result_text)
    except Exception as exc:
        logger.exception("Failed to fetch sticker set")
        await send_text_chunks(update, context, f"Pack fetch করতে সমস্যা হয়েছে: {exc}")


async def cmd_ids(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = " ".join(context.args or []).strip()
    if not text:
        await send_text_chunks(
            update,
            context,
            "Usage:\n/ids https://t.me/addemoji/prem_28a5b_by_TgEmojis_bot",
        )
        return
    await process_link(update, context, text)


async def handle_plain_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message or not update.effective_message.text:
        return

    text = update.effective_message.text.strip()
    if text.startswith("/"):
        return

    if ADD_LINK_RE.search(text) or "t.me/addemoji/" in text or "t.me/addstickers/" in text:
        await process_link(update, context, text)
        return

    await send_text_chunks(
        update,
        context,
        "Telegram pack link পাঠান। Example:\nhttps://t.me/addemoji/prem_28a5b_by_TgEmojis_bot",
    )


async def post_init(application: Application) -> None:
    try:
        await application.bot.set_my_commands(BOT_COMMANDS)
        logger.info("Bot commands registered")
    except Exception:
        logger.exception("Failed to register bot commands")


def _health_payload() -> bytes:
    payload = {
        "ok": True,
        "service": "telegram-custom-emoji-id-bot",
        "mode": "polling",
    }
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def run_render_health_server() -> None:
    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path not in ("/", "/healthz"):
                self.send_response(404)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(b'{"ok": false, "error": "not_found"}')
                return

            body = _health_payload()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args) -> None:
            return

    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    logger.info("Health server started on port %s", PORT)
    server.serve_forever()


def build_app() -> Application:
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing")

    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("commands", cmd_commands))
    application.add_handler(CommandHandler("ping", cmd_ping))
    application.add_handler(CommandHandler("id", cmd_id))
    application.add_handler(CommandHandler("ids", cmd_ids))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_plain_text))

    return application


def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN is missing")

    threading.Thread(target=run_render_health_server, daemon=True).start()
    app = build_app()

    logger.info("Starting Telegram Custom Emoji ID Bot in polling mode")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)
    finally:
        try:
            loop.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
