import logging
import os
from dataclasses import asdict
from datetime import datetime
from io import BytesIO

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import get_settings, save_settings
from image_processor import process_image
from printer import print_image

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Parameter registry for /set
# Each entry: alias -> (section, field, type, constraint)
#   type in: "float" | "int" | "bool" | "str" | "choice"
#   constraint: (min, max) for numeric, list of allowed values for choice, None otherwise
# ---------------------------------------------------------------------------
_PARAMS: dict[str, tuple] = {
    "dither":     ("image",   "dither_algorithm", "choice", ["bayer8x8", "bayer4x4", "floyd_steinberg", "atkinson", "threshold"]),
    "contrast":   ("image",   "contrast",         "float",  (0.5, 2.0)),
    "brightness": ("image",   "brightness",       "float",  (0.5, 2.0)),
    "sharpness":  ("image",   "sharpness",        "float",  (0.0, 3.0)),
    "grayscale":  ("image",   "grayscale_mode",   "choice", ["luminosity", "average", "red", "green", "blue"]),
    "gamma":      ("image",   "gamma",            "float",  (0.3, 2.5)),
    "threshold":  ("image",   "threshold",        "int",    (0, 255)),
    "blur":       ("image",   "pre_blur",         "float",  (0.0, 5.0)),
    "vignette":   ("image",   "vignette",         "float",  (0.0, 1.0)),
    "grain":      ("image",   "grain",            "float",  (0.0, 1.0)),
    "posterize":  ("image",   "posterize_bits",   "int",    (0, 7)),
    "invert":     ("image",   "invert",           "bool",   None),
    "rotate":     ("image",   "auto_rotate",      "bool",   None),
    "caption":    ("caption", "enabled",          "bool",   None),
    "location":   ("caption", "location",         "str",    None),
    "date":       ("caption", "show_date",        "bool",   None),
    "align":      ("printer", "align",            "choice", ["left", "center", "right"]),
    "width":      ("printer", "max_width",        "int",    (1, 832)),
}

_BOOL_TRUE  = {"on", "true", "yes", "1"}
_BOOL_FALSE = {"off", "false", "no", "0"}


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


def _img_to_bytes(img) -> BytesIO:
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def _format_status(s) -> str:
    d = asdict(s)
    img = d["image"]
    cap = d["caption"]
    prn = d["printer"]
    return (
        f"Image\n"
        f"  dither     : {img['dither_algorithm']}\n"
        f"  grayscale  : {img['grayscale_mode']}\n"
        f"  contrast   : {img['contrast']}\n"
        f"  brightness : {img['brightness']}\n"
        f"  sharpness  : {img['sharpness']}\n"
        f"  gamma      : {img['gamma']}\n"
        f"  threshold  : {img['threshold']}\n"
        f"  blur       : {img['pre_blur']}\n"
        f"  vignette   : {img['vignette']}\n"
        f"  grain      : {img['grain']}\n"
        f"  posterize  : {img['posterize_bits']}\n"
        f"  invert     : {img['invert']}\n"
        f"  rotate     : {img['auto_rotate']}\n"
        f"\nCaption\n"
        f"  caption    : {cap['enabled']}\n"
        f"  location   : {cap['location']}\n"
        f"  date       : {cap['show_date']}\n"
        f"\nPrinter\n"
        f"  align      : {prn['align']}\n"
        f"  width      : {prn['max_width']}px"
    )


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Thermal Printer Bot\n\n"
        "Send me a photo — I'll show a preview before printing.\n\n"
        "Commands:\n"
        "/status — show all current settings\n"
        "/set <param> <value> — change a setting\n"
        "/params — list all settable parameters\n"
        "/start — show this message"
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update.effective_user.id):
        await update.message.reply_text("Unauthorized.")
        return
    s = get_settings()
    await update.message.reply_text(f"```\n{_format_status(s)}\n```", parse_mode="MarkdownV2")


async def cmd_params(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update.effective_user.id):
        await update.message.reply_text("Unauthorized.")
        return
    lines = ["/set <param> <value>\n"]
    for alias, (section, field, kind, constraint) in _PARAMS.items():
        if kind == "choice":
            extra = " | ".join(constraint)
        elif kind == "float":
            extra = f"{constraint[0]} – {constraint[1]}"
        elif kind == "int":
            extra = f"{constraint[0]} – {constraint[1]}"
        elif kind == "bool":
            extra = "on | off"
        else:
            extra = "text"
        lines.append(f"  {alias:<12} {extra}")
    await update.message.reply_text("```\n" + "\n".join(lines) + "\n```", parse_mode="MarkdownV2")


async def cmd_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update.effective_user.id):
        await update.message.reply_text("Unauthorized.")
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: /set <param> <value>\nSee /params for the list.")
        return

    alias = args[0].lower()
    raw = " ".join(args[1:])  # allow multi-word values (e.g. location names)

    if alias not in _PARAMS:
        await update.message.reply_text(
            f"Unknown parameter '{alias}'.\nSee /params for the list."
        )
        return

    section, field, kind, constraint = _PARAMS[alias]
    settings = get_settings()
    section_obj = getattr(settings, section)

    try:
        if kind == "float":
            value = round(float(raw), 2)
            lo, hi = constraint
            if not (lo <= value <= hi):
                raise ValueError(f"must be between {lo} and {hi}")
        elif kind == "int":
            value = int(raw)
            lo, hi = constraint
            if not (lo <= value <= hi):
                raise ValueError(f"must be between {lo} and {hi}")
        elif kind == "bool":
            if raw.lower() in _BOOL_TRUE:
                value = True
            elif raw.lower() in _BOOL_FALSE:
                value = False
            else:
                raise ValueError("use on or off")
        elif kind == "choice":
            value = raw.lower()
            if value not in constraint:
                raise ValueError(f"allowed values: {', '.join(constraint)}")
        else:  # str
            value = raw
    except ValueError as exc:
        await update.message.reply_text(f"Invalid value for '{alias}': {exc}.")
        return

    setattr(section_obj, field, value)
    save_settings(settings)
    await update.message.reply_text(f"{alias} = {value}")


# ---------------------------------------------------------------------------
# Photo handler — process, send preview, ask for confirmation
# ---------------------------------------------------------------------------

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update.effective_user.id):
        await update.message.reply_text("Unauthorized.")
        return

    settings = get_settings()
    photo = update.message.photo[-1]  # highest resolution
    file = await context.bot.get_file(photo.file_id)
    image_bytes = await file.download_as_bytearray()

    status_msg = await update.message.reply_text("Processing…")

    try:
        img = process_image(bytes(image_bytes), settings)
        caption = _build_caption(settings)

        # Store for later retrieval when the user confirms
        context.user_data["pending"] = {"img": img, "caption": caption}

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Print", callback_data="print_confirm"),
            InlineKeyboardButton("❌ Cancel", callback_data="print_cancel"),
        ]])
        await status_msg.delete()
        await update.message.reply_photo(
            photo=_img_to_bytes(img),
            caption="Preview — print this?",
            reply_markup=keyboard,
        )
    except Exception as e:
        logger.error("Processing failed: %s", e, exc_info=True)
        await status_msg.edit_text(f"Error: {e}")


# ---------------------------------------------------------------------------
# Callback handler — print confirmation
# ---------------------------------------------------------------------------

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == "print_cancel":
        context.user_data.pop("pending", None)
        await query.edit_message_caption("Cancelled.")
        return

    if query.data == "print_confirm":
        pending = context.user_data.pop("pending", None)
        if pending is None:
            await query.edit_message_caption("Session expired — please resend the photo.")
            return
        try:
            print_image(pending["img"], pending["caption"])
            await query.edit_message_caption("Printed!")
        except Exception as e:
            logger.error("Print failed: %s", e, exc_info=True)
            await query.edit_message_caption(f"Print error: {e}")


# ---------------------------------------------------------------------------
# Bot factory
# ---------------------------------------------------------------------------

def create_bot() -> Application:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("status",  cmd_status))
    app.add_handler(CommandHandler("params",  cmd_params))
    app.add_handler(CommandHandler("set",     cmd_set))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    return app
