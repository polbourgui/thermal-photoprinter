# thermal-photoprinter

Turn a thermal printer into a photo printer, controllable entirely from Telegram.

Originally built around IMAP email fetching — now a Telegram bot with a web UI, a full image processing pipeline, and persistent settings.

---

## Features

- **Telegram bot** — send a photo, get a preview, confirm or cancel before printing
- **Text commands** — change any setting live via `/set`, no config file editing needed
- **Web UI** — adjust and preview settings from a browser (FastAPI, port 8080)
- **Image processing pipeline** — dithering, tone adjustments, gamma, vignette, grain, posterization, inversion, and more
- **Auto-caption** — optional date/time and location printed below each photo
- **Authorization** — restrict the bot to a list of Telegram user IDs

---

## How it works

```
User sends photo on Telegram
  → Bot downloads + processes image
  → Bot sends preview with [✅ Print] [❌ Cancel]
  → User confirms → ESC/POS command sent to thermal printer
```

Settings persist to `config/settings.json` and apply to all future prints.

---

## Getting started

### Requirements

- Python 3.11+
- A thermal printer with USB, compatible with python-escpos
- A Telegram bot token ([BotFather](https://t.me/BotFather))

### Installation

```bash
pip install -r requirements.txt
cp .env.example .env
# edit .env with your values
python -m src.main
```

### With Docker

```bash
docker compose up
```

### Environment variables

| Variable | Required | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes | Token from BotFather |
| `TELEGRAM_ALLOWED_USER_IDS` | No | Comma-separated user IDs (empty = allow all) |
| `PRINTER_VENDOR_ID` | Yes | USB vendor ID (hex) |
| `PRINTER_PRODUCT_ID` | Yes | USB product ID (hex) |

---

## Telegram commands

| Command | Description |
|---|---|
| `/start` | Show help |
| `/status` | Display all current settings |
| `/params` | List all settable parameters with allowed values |
| `/set <param> <value>` | Change a setting |

### `/set` parameters

| Parameter | Type | Range / Values |
|---|---|---|
| `dither` | choice | `bayer8x8` · `bayer4x4` · `floyd_steinberg` · `atkinson` · `threshold` |
| `contrast` | float | 0.5 – 2.0 |
| `brightness` | float | 0.5 – 2.0 |
| `sharpness` | float | 0.0 – 3.0 |
| `grayscale` | choice | `luminosity` · `average` · `red` · `green` · `blue` |
| `gamma` | float | 0.3 – 2.5 (< 1 lightens, > 1 darkens) |
| `threshold` | int | 0 – 255 |
| `blur` | float | 0.0 – 5.0 |
| `vignette` | float | 0.0 – 1.0 |
| `grain` | float | 0.0 – 1.0 |
| `posterize` | int | 0 (off) – 7 |
| `invert` | bool | `on` / `off` |
| `rotate` | bool | `on` / `off` |
| `caption` | bool | `on` / `off` |
| `location` | text | any text |
| `date` | bool | `on` / `off` |
| `align` | choice | `left` · `center` · `right` |
| `width` | int | 1 – 832 px |

Examples:

```
/set dither atkinson
/set gamma 0.75
/set grayscale red
/set invert on
/set location Paris
```

---

## Project structure

```
src/
├── main.py             # Entry point — starts bot + web server concurrently
├── config.py           # Settings dataclasses + JSON persistence
├── image_processor.py  # Full image processing pipeline
├── printer.py          # ESC/POS printer interface
├── telegram_bot.py     # Telegram handlers (commands, photo, callbacks)
└── web/
    ├── app.py          # FastAPI app (settings form, preview endpoint)
    └── templates/
        └── index.html  # Web UI
config/
└── settings.json       # Persisted settings (auto-generated)
```

---

## Dependencies

- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) 20.x
- [Pillow](https://python-pillow.org/) ≥ 10.0
- [numpy](https://numpy.org/)
- [python-escpos](https://github.com/python-escpos/python-escpos) ≥ 3.0
- [FastAPI](https://fastapi.tiangolo.com/) + [uvicorn](https://www.uvicorn.org/)
- [python-dotenv](https://github.com/theskumar/python-dotenv)
