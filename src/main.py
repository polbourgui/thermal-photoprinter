import logging
import os
import sys
import threading

import uvicorn
from dotenv import load_dotenv

from config import load_settings
from telegram_bot import create_bot

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)-20s %(levelname)-8s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def _run_web() -> None:
    port = int(os.getenv("WEB_PORT", "8080"))
    uvicorn.run(
        "web.app:app",
        host="0.0.0.0",
        port=port,
        log_level="warning",
    )


def main() -> None:
    load_settings()

    web_thread = threading.Thread(target=_run_web, daemon=True, name="web")
    web_thread.start()
    logger.info("Web interface started on port %s", os.getenv("WEB_PORT", "8080"))

    logger.info("Starting Telegram bot...")
    bot = create_bot()
    bot.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
