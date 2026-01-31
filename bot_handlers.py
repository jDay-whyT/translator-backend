import html
import io
import os
import time
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from gpt_prompts import TARGET_PROMPTS
from stt import transcribe
from translate_core import translate_core


BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_ALLOWED_USERNAMES = {
    value.strip().lower()
    for value in os.getenv("TG_ALLOWED_USERNAMES", "").split(",")
    if value.strip()
}

TEXT_CACHE_TTL_SECONDS = 45 * 60
_TEXT_CACHE: dict[str, tuple[float, str, str]] = {}
_PROCESSED_CALLBACKS: set[str] = set()


def _has_access(username: Optional[str]) -> bool:
    if not TG_ALLOWED_USERNAMES:
        return True
    if not username:
        return False
    return username.lower() in TG_ALLOWED_USERNAMES


def _make_cache_key(chat_id: int, source_message_id: int) -> str:
    return f"{chat_id}:{source_message_id}"


def _store_cached_text(
    chat_id: int, source_message_id: int, text: str, source: str
) -> None:
    expires_at = time.time() + TEXT_CACHE_TTL_SECONDS
    _TEXT_CACHE[_make_cache_key(chat_id, source_message_id)] = (
        expires_at,
        text,
        source,
    )


def _get_cached_text(chat_id: int, source_message_id: int) -> Optional[tuple[str, str]]:
    key = _make_cache_key(chat_id, source_message_id)
    cached = _TEXT_CACHE.get(key)
    if not cached:
        return None
    expires_at, text, source = cached
    if time.time() > expires_at:
        _TEXT_CACHE.pop(key, None)
        return None
    return text, source


def _cleanup_caches() -> None:
    """Remove expired entries from cache and old processed callbacks."""
    now = time.time()
    # Clean expired text cache entries
    expired_keys = [
        key for key, (expires_at, _, _) in _TEXT_CACHE.items() if now > expires_at
    ]
    for key in expired_keys:
        _TEXT_CACHE.pop(key, None)

    # Keep only recent callbacks (last 5 minutes worth)
    # Callback IDs are unique, so we can safely clear old ones
    if len(_PROCESSED_CALLBACKS) > 1000:
        _PROCESSED_CALLBACKS.clear()


def _build_root_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("EN", callback_data="lang:set:en"),
            InlineKeyboardButton("RU", callback_data="lang:set:ru"),
        ],
        [
            InlineKeyboardButton("ES ▸", callback_data="lang:root:es"),
            InlineKeyboardButton("PT ▸", callback_data="lang:root:pt"),
        ],
    ]
    return InlineKeyboardMarkup(rows)


def _build_es_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("ES (ES)", callback_data="lang:set:es-es"),
            InlineKeyboardButton(
                "ES (LATAM)", callback_data="lang:set:es-latam"
            ),
        ],
        [InlineKeyboardButton("⬅ Back", callback_data="lang:back")],
    ]
    return InlineKeyboardMarkup(rows)


def _build_pt_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("PT-BR", callback_data="lang:set:pt-br"),
            InlineKeyboardButton("PT-PT", callback_data="lang:set:pt-pt"),
        ],
        [InlineKeyboardButton("⬅ Back", callback_data="lang:back")],
    ]
    return InlineKeyboardMarkup(rows)


def _format_translation(translation: str) -> str:
    # Self-test: use HTML <pre> so Telegram keeps monospace + copy-friendly block;
    # escape only HTML chars to prevent tag injection without touching whitespace/emoji.
    escaped = html.escape(translation, quote=False)
    return f"<pre>{escaped}</pre>"


# Self-check:
# - ES/PT submenus open via edit_message_reply_markup; Back returns to root.
# - lang:set:* uses cached source message; formatting uses HTML <pre> with escaping.


async def _guard_access(update: Update) -> bool:
    user = update.effective_user
    if not _has_access(user.username if user else None):
        if update.message:
            await update.message.reply_text("Access denied.")
        elif update.callback_query:
            await update.callback_query.answer("Access denied.", show_alert=True)
        return False
    return True


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard_access(update):
        return
    if update.message:
        await update.message.reply_text(
            "Send me text or a voice message and choose a target language."
        )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard_access(update):
        return
    if not update.message or not update.message.text:
        return
    text = update.message.text.strip()
    if not text:
        return
    _store_cached_text(update.effective_chat.id, update.message.message_id, text, "text")
    await update.message.reply_text(
        "Choose a target language:",
        reply_markup=_build_root_keyboard(),
        reply_to_message_id=update.message.message_id,
    )


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard_access(update):
        return
    if not update.message or not update.message.voice:
        return
    voice = update.message.voice
    file = await voice.get_file()
    audio_bytes = await file.download_as_bytearray()
    text = transcribe(bytes(audio_bytes))
    if not text:
        await update.message.reply_text("Could not transcribe the audio.")
        return
    _store_cached_text(update.effective_chat.id, update.message.message_id, text, "stt")
    await update.message.reply_text(
        f"Transcribed text:\n\n{text}\n\nChoose a target language:",
        reply_markup=_build_root_keyboard(),
        reply_to_message_id=update.message.message_id,
    )


async def handle_language_choice(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not await _guard_access(update):
        return
    query = update.callback_query
    if not query:
        return

    # Prevent duplicate callback processing
    callback_id = query.id
    if callback_id in _PROCESSED_CALLBACKS:
        await query.answer()
        return
    _PROCESSED_CALLBACKS.add(callback_id)

    # Periodic cleanup
    if len(_TEXT_CACHE) % 50 == 0:
        _cleanup_caches()

    await query.answer()
    data = query.data or ""

    # Handle submenu navigation
    if data == "lang:root:es":
        try:
            await query.edit_message_reply_markup(reply_markup=_build_es_keyboard())
        except BadRequest as e:
            # Ignore "message is not modified" errors
            if "message is not modified" not in str(e).lower():
                raise
        return

    if data == "lang:root:pt":
        try:
            await query.edit_message_reply_markup(reply_markup=_build_pt_keyboard())
        except BadRequest as e:
            if "message is not modified" not in str(e).lower():
                raise
        return

    if data == "lang:back":
        try:
            await query.edit_message_reply_markup(reply_markup=_build_root_keyboard())
        except BadRequest as e:
            if "message is not modified" not in str(e).lower():
                raise
        return

    # Handle language selection
    if not data.startswith("lang:set:"):
        return

    target = data.split(":", 2)[-1]
    if target not in TARGET_PROMPTS:
        try:
            await query.edit_message_text("Unsupported target language.")
        except BadRequest as e:
            if "message is not modified" not in str(e).lower():
                raise
        return

    reply_to = query.message.reply_to_message if query.message else None
    source_message_id = reply_to.message_id if reply_to else None
    if not source_message_id:
        try:
            await query.edit_message_text("No text to translate. Send a message first.")
        except BadRequest as e:
            if "message is not modified" not in str(e).lower():
                raise
        return

    chat_id = update.effective_chat.id if update.effective_chat else 0
    if not chat_id:
        try:
            await query.edit_message_text("No text to translate. Send a message first.")
        except BadRequest as e:
            if "message is not modified" not in str(e).lower():
                raise
        return

    cached = _get_cached_text(chat_id, source_message_id)
    if not cached:
        try:
            await query.edit_message_text("No text to translate. Send a message first.")
        except BadRequest as e:
            if "message is not modified" not in str(e).lower():
                raise
        return

    text, source = cached
    result = translate_core(text, target, source=source)

    if not result.get("ok"):
        error = result.get("error", "Translation failed")
        try:
            await query.edit_message_text(f"Translation error: {error}")
        except BadRequest as e:
            if "message is not modified" not in str(e).lower():
                raise
        return

    translation = result.get("translation") or result.get("text", "")
    provider = result.get("provider_used", "unknown")
    formatted_translation = _format_translation(translation)
    message_text = f"{formatted_translation}\n\nProvider: {provider}"

    if len(message_text) > 3900:
        translation_bytes = io.BytesIO(translation.encode("utf-8"))
        translation_bytes.name = "translation.txt"
        try:
            await query.edit_message_text(
                f"Sent as file.\n\nProvider: {provider}",
                parse_mode=None,
                reply_markup=None,
            )
        except BadRequest as e:
            if "message is not modified" not in str(e).lower():
                raise
        if query.message:
            await query.message.reply_document(translation_bytes)
        return

    try:
        await query.edit_message_text(message_text, parse_mode=ParseMode.HTML)
    except BadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise


def build_application() -> Application:
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing")
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_handler(CallbackQueryHandler(handle_language_choice))
    return application
