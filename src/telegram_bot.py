import logging
import os
from datetime import datetime

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from config import get_settings
from image_processor import process_image
from printer import print_image

logger = logging.getLogger(__name__)


def _allowed_users() -> set[int]:
    ids_str = os.getenv("TELEGRAM_ALLOWED_USER_IDS", "")
    return {int(uid.strip()) for uid in ids_str.split(",") if uid.strip()}


def _is_authorized(user_id: int) -> bool:
    allowed = _allowed_users()
    return not allowed or user_id in allowed


def _build_caption(settings) -> str | None:
    if not settings.caption.enabled:
        return None
    parts = []
    if settings.caption.show_date:
        parts.append(datetime.now().strftime("%d/%m/%y %H:%M"))
    if settings.caption.location:
        parts.append(f"@ {settings.caption.location}")
    return "\n" + " ".join(parts) if parts else None


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Thermal Printer Bot\n\n"
        "Send me a photo to print it.\n"
        "/status — show current settings\n"
        "/start — show this message"
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update.effective_user.id):
        await update.message.reply_text("Unauthorized.")
        return

    s = get_settings()
    text = (
        f"Image processing\n"
        f"  Dithering : {s.image.dither_algorithm}\n"
        f"  Contrast  : {s.image.contrast}\n"
        f"  Brightness: {s.image.brightness}\n"
        f"  Sharpness : {s.image.sharpness}\n"
        f"\nCaption\n"
        f"  Enabled   : {s.caption.enabled}\n"
        f"  Location  : {s.caption.location}\n"
        f"  Show date : {s.caption.show_date}\n"
        f"\nPrinter\n"
        f"  Max width : {s.printer.max_width}px\n"
        f"  Align     : {s.printer.align}"
    )
    await update.message.reply_text(f"```\n{text}\n```", parse_mode="MarkdownV2")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update.effective_user.id):
        await update.message.reply_text("Unauthorized.")
        return

    settings = get_settings()
    photo = update.message.photo[-1]  # highest resolution available
    file = await context.bot.get_file(photo.file_id)
    image_bytes = await file.download_as_bytearray()

    status_msg = await update.message.reply_text("Processing...")

    try:
        img = process_image(bytes(image_bytes), settings)
        caption = _build_caption(settings)
        print_image(img, caption)
        await status_msg.edit_text("Printed!")
    except Exception as e:
        logger.error("Print failed: %s", e, exc_info=True)
        await status_msg.edit_text(f"Error: {e}")


def create_bot() -> Application:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    return app
