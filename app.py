from __future__ import annotations

import logging
import sys

import uvicorn

from api import app
from config import settings


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        stream=sys.stdout,
    )


if __name__ == "__main__":
    configure_logging()
    logging.getLogger("rb_device_agent").info(
        "Starting %s v%s on http://%s:%s",
        settings.app_name,
        settings.version,
        settings.host,
        settings.port,
    )
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")
