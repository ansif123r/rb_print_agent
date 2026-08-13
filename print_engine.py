from __future__ import annotations

import platform


class PrintEngine:
    """Low-level Windows RAW printer output."""

    def __init__(self) -> None:
        if platform.system() != "Windows":
            raise RuntimeError("RB Device Agent printing currently requires Windows.")

        try:
            import win32print  # type: ignore
        except ImportError as exc:
            raise RuntimeError("pywin32 is required for Windows printing.") from exc

        self._win32print = win32print

    def raw_text(self, printer_name: str, text: str) -> None:
        if not printer_name.strip():
            raise ValueError("Printer name is required.")
        if not text:
            raise ValueError("Print content is empty.")

        handle = self._win32print.OpenPrinter(printer_name)
        try:
            self._win32print.StartDocPrinter(handle, 1, ("RB Device Agent", None, "RAW"))
            try:
                self._win32print.StartPagePrinter(handle)
                try:
                    payload = text.encode("cp437", errors="replace")
                    self._win32print.WritePrinter(handle, payload)
                finally:
                    self._win32print.EndPagePrinter(handle)
            finally:
                self._win32print.EndDocPrinter(handle)
        finally:
            self._win32print.ClosePrinter(handle)

    def escpos_test_receipt(self, printer_name: str) -> None:
        # ESC/POS: initialize, center, bold title, normal text, cut.
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

        handle = self._win32print.OpenPrinter(printer_name)
        try:
            self._win32print.StartDocPrinter(handle, 1, ("RB Device Agent Test", None, "RAW"))
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
