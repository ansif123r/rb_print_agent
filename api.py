from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from config import settings
from print_engine import PrintEngine
from printer_manager import PrinterManager

logger = logging.getLogger("rb_device_agent")

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    docs_url="/docs",
    redoc_url=None,
)


class TestPrintRequest(BaseModel):
    printer: str = Field(min_length=1)
    text: str | None = None


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "app": settings.app_name, "version": settings.version}


@app.get("/printers")
def printers() -> dict[str, Any]:
    try:
        manager = PrinterManager()
        items = manager.list_printers()
        default = manager.get_default_printer()
        return {
            "printers": [
                {"name": item.name, "port": item.port, "driver": item.driver, "status": item.status}
                for item in items
            ],
            "default_printer": default,
        }
    except Exception as exc:
        logger.exception("Printer discovery failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/test-print")
def test_print(request: TestPrintRequest) -> dict[str, Any]:
    try:
        manager = PrinterManager()
        if not manager.printer_exists(request.printer):
            raise HTTPException(status_code=404, detail=f"Printer not found: {request.printer}")

        engine = PrintEngine()
        if request.text:
            engine.raw_text(request.printer, request.text)
        else:
            engine.escpos_test_receipt(request.printer)

        return {"status": "printed", "printer": request.printer}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Print job failed for %s", request.printer)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
