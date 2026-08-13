from __future__ import annotations

import logging
import sys
import threading

import uvicorn

from api import app
from config import settings
from queue_worker import QueueWorker


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        stream=sys.stdout,
    )


if __name__ == "__main__":
    configure_logging()
    logger = logging.getLogger("rb_device_agent")
    logger.info(
        "Starting %s v%s on http://%s:%s",
        settings.app_name,
        settings.version,
        settings.host,
        settings.port,
    )

    worker = QueueWorker()
    if settings.erpnext_url and settings.erpnext_token:
        threading.Thread(target=worker.run, name="rb-print-queue", daemon=True).start()
    else:
        logger.warning("ERPNext queue worker disabled: RB_AGENT_ERPNEXT_URL or RB_AGENT_TOKEN is missing.")

    try:
        uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")
    finally:
        worker.stop()
