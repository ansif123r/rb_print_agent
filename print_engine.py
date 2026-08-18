from __future__ import annotations

import base64
import platform


class PrintEngine:
    """Windows RAW printer output with direct ERPNext ESC/POS support."""

    RAW_PREFIX = "RBRAW1:"

    def __init__(self) -> None:
        if platform.system() != "Windows":
            raise RuntimeError("RB Device Agent printing currently requires Windows.")

        try:
            import win32print  # type: ignore
        except ImportError as exc:
            raise RuntimeError("pywin32 is required for Windows printing.") from exc

        self._win32print = win32print

    def raw_bytes(self, printer_name: str, payload: bytes) -> None:
        if not printer_name.strip():
            raise ValueError("Printer name is required.")
        if not payload:
            raise ValueError("Print content is empty.")

        handle = self._win32print.OpenPrinter(printer_name)
        try:
            self._win32print.StartDocPrinter(handle, 1, ("RB Device Agent", None, "RAW"))
            try:
                self._win32print.StartPagePrinter(handle)
                try:
                    self._win32print.WritePrinter(handle, payload)
                finally:
                    self._win32print.EndPagePrinter(handle)
            finally:
                self._win32print.EndDocPrinter(handle)
        finally:
            self._win32print.ClosePrinter(handle)

    def raw_text(self, printer_name: str, text: str) -> None:
        self.raw_bytes(printer_name, text.encode("latin-1", errors="replace"))

    def escpos_test_receipt(self, printer_name: str) -> None:
        payload = (
            b"\x1b@"
            b"\x1ba\x01"
            b"\x1bE\x01"
            b"RB DEVICE AGENT\n"
            b"\x1bE\x00"
            b"\n"
            b"USB PRINTER TEST\n"
            b"------------------------------\n"
            b"Printer communication is working.\n"
            b"R B FRESH MART\n"
            b"\n\n\n"
            b"\x1dV\x00"
        )
        self.raw_bytes(printer_name, payload)

    def rbraw_payload_to_bytes(self, payload: str) -> bytes:
        if not payload.startswith(self.RAW_PREFIX):
            raise ValueError("Unsupported direct ESC/POS payload format.")
        encoded = payload[len(self.RAW_PREFIX):].strip()
        if not encoded:
            raise ValueError("RBRAW1 payload is empty.")
        try:
            return base64.b64decode(encoded, validate=True)
        except Exception as exc:
            raise ValueError("Invalid RBRAW1 base64 payload.") from exc

    def print_payload(self, printer_name: str, payload: str) -> None:
        if payload.startswith(self.RAW_PREFIX):
            self.raw_bytes(printer_name, self.rbraw_payload_to_bytes(payload))
            return

        # Keep the old text fallback for non-POS/legacy jobs.
        self.raw_text(printer_name, payload)
