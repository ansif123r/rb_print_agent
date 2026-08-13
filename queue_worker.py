from __future__ import annotations

import logging
import threading
import time
from typing import Any

from config import settings
from erpnext_client import ERPNextClient
from print_engine import PrintEngine

logger = logging.getLogger("rb_device_agent.queue")


class QueueWorker:
    def __init__(self) -> None:
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        logger.info("ERPNext print queue worker started for printer %s", settings.printer_name)
        while not self._stop.is_set():
            try:
                self.process_once()
            except Exception:
                logger.exception("Print queue polling failed")
            self._stop.wait(settings.poll_interval)

    def process_once(self) -> None:
        if not settings.erpnext_url or not settings.erpnext_token:
            return

        client = ERPNextClient()
        jobs = client.get_pending_jobs(settings.printer_name)
        if not jobs:
            return

        engine = PrintEngine()
        for job in jobs:
            job_name = str(job["name"])
            try:
                client.update_job_status(job_name, "Printing")
                payload = job.get("payload")
                if not payload:
                    raise ValueError("Print job has no payload")

                copies = max(1, min(int(job.get("copies") or 1), 20))
                for _ in range(copies):
                    engine.raw_text(settings.printer_name, str(payload))

                client.update_job_status(job_name, "Printed")
                logger.info("Printed ERPNext job %s", job_name)
            except Exception as exc:
                logger.exception("ERPNext print job %s failed", job_name)
                try:
                    client.update_job_status(job_name, "Failed", str(exc))
                except Exception:
                    logger.exception("Could not report failure for job %s", job_name)
