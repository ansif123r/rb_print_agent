from __future__ import annotations

import base64
import platform


class PrintEngine:
    """Windows RAW printer output with ESC/POS and ERPNext PDF raster support."""

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

    @staticmethod
    def _mono_raster_rows(pix) -> bytes:
        width = pix.width
        height = pix.height
        channels = pix.n
        samples = pix.samples
        row_bytes = (width + 7) // 8
        output = bytearray(row_bytes * height)

        for y in range(height):
            src_row = y * width * channels
            dst_row = y * row_bytes
            for x in range(width):
                offset = src_row + x * channels
                r = samples[offset]
                g = samples[offset + 1]
                b = samples[offset + 2]
                gray = (299 * r + 587 * g + 114 * b) // 1000
                if gray < 180:
                    output[dst_row + (x // 8)] |= 0x80 >> (x % 8)

        return bytes(output)

    @staticmethod
    def _escpos_raster(width: int, height: int, bitmap: bytes) -> bytes:
        row_bytes = (width + 7) // 8
        data = bytearray()
        data += b"\x1dv0\x00"
        data += bytes((row_bytes & 0xFF, (row_bytes >> 8) & 0xFF))
        data += bytes((height & 0xFF, (height >> 8) & 0xFF))
        data += bitmap
        return bytes(data)

    def pdf_bytes_to_escpos(self, pdf_bytes: bytes, target_width: int = 576) -> bytes:
        try:
            import fitz  # PyMuPDF
        except ImportError as exc:
            raise RuntimeError("PyMuPDF is required for ERPNext PDF printing.") from exc

        document = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            if document.page_count == 0:
                raise ValueError("PDF contains no pages.")

            output = bytearray(b"\x1b@\x1ba\x00")
            for page_index in range(document.page_count):
                page = document.load_page(page_index)
                if page.rect.width <= 0:
                    continue

                scale = target_width / page.rect.width
                pix = page.get_pixmap(
                    matrix=fitz.Matrix(scale, scale),
                    colorspace=fitz.csRGB,
                    alpha=False,
                )
                bitmap = self._mono_raster_rows(pix)
                output += self._escpos_raster(pix.width, pix.height, bitmap)
                if page_index < document.page_count - 1:
                    output += b"\n\n"

            output += b"\n\n\n\x1dV\x00"
            return bytes(output)
        finally:
            document.close()

    def rbpdf_payload_to_bytes(self, payload: str) -> bytes:
        if not payload.startswith("RBPDF1:"):
            raise ValueError("Unsupported PDF print payload format.")
        encoded = payload[len("RBPDF1:"):].strip()
        if not encoded:
            raise ValueError("RBPDF1 payload is empty.")
        try:
            return base64.b64decode(encoded, validate=True)
        except Exception as exc:
            raise ValueError("Invalid RBPDF1 base64 payload.") from exc

    def print_payload(self, printer_name: str, payload: str) -> None:
        if payload.startswith("RBPDF1:"):
            pdf_bytes = self.rbpdf_payload_to_bytes(payload)
            self.raw_bytes(printer_name, self.pdf_bytes_to_escpos(pdf_bytes))
            return

        self.raw_text(printer_name, payload)
