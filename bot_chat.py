import os
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
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

LANGUAGE_OPTIONS = [
    ("en", "EN"),
    ("ru", "RU"),
    ("es-es", "ES (ES)"),
    ("es-latam", "ES (LATAM)"),
    ("pt-br", "PT-BR"),
    ("pt-pt", "PT-PT"),
]


def _has_access(username: Optional[str]) -> bool:
    if not TG_ALLOWED_USERNAMES:
        return True
    if not username:
        return False
    return username.lower() in TG_ALLOWED_USERNAMES


def _build_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for target, label in LANGUAGE_OPTIONS:
        rows.append([InlineKeyboardButton(label, callback_data=f"target:{target}")])
    return InlineKeyboardMarkup(rows)


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
    context.user_data["pending_text"] = text
    await update.message.reply_text(
        "Choose a target language:",
        reply_markup=_build_keyboard(),
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
    context.user_data["pending_text"] = text
    await update.message.reply_text(
        f"Transcribed text:\n\n{text}\n\nChoose a target language:",
        reply_markup=_build_keyboard(),
    )


async def handle_language_choice(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not await _guard_access(update):
        return
    query = update.callback_query
    if not query:
        return
    await query.answer()
    data = query.data or ""
    if not data.startswith("target:"):
        return
    target = data.split(":", 1)[1]
    if target not in TARGET_PROMPTS:
        await query.edit_message_text("Unsupported target language.")
        return
    text = context.user_data.get("pending_text", "")
    if not text:
        await query.edit_message_text("No text to translate. Send a message first.")
        return
    result = translate_core(text, target)
    if not result.get("ok"):
        error = result.get("error", "Translation failed")
        await query.edit_message_text(f"Translation error: {error}")
        return
    translation = result.get("translation") or result.get("text", "")
    provider = result.get("provider_used", "unknown")
    await query.edit_message_text(
        f"{translation}\n\n_Provider: {provider}_",
        parse_mode=ParseMode.MARKDOWN,
    )


def build_application() -> Application:
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing")
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_handler(CallbackQueryHandler(handle_language_choice))
    return application


def main() -> None:
    application = build_application()
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
