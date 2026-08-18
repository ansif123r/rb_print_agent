from __future__ import annotations

import platform


class PrintEngine:
    """Low-level Windows RAW printer output."""

    MAX_DOTS = 576
    THRESHOLD = 180

    def __init__(self) -> None:
        if platform.system() != "Windows":
            raise RuntimeError("RB Device Agent printing currently requires Windows.")

        try:
            import win32print  # type: ignore
        except ImportError as exc:
            raise RuntimeError("pywin32 is required for Windows printing.") from exc

        self._win32print = win32print

    def _write_raw(self, printer_name: str, payload: bytes, job_name: str = "RB Device Agent") -> None:
        if not printer_name.strip():
            raise ValueError("Printer name is required.")
        if not payload:
            raise ValueError("Print content is empty.")

        handle = self._win32print.OpenPrinter(printer_name)
        try:
            self._win32print.StartDocPrinter(handle, 1, (job_name, None, "RAW"))
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
        payload = text.encode("latin-1", errors="replace")
        self._write_raw(printer_name, payload)

    def raw_bytes(self, printer_name: str, payload: bytes) -> None:
        self._write_raw(printer_name, payload)

    def pdf(self, printer_name: str, pdf_bytes: bytes) -> None:
        """Render an ERPNext PDF print format to ESC/POS raster and print it RAW."""
        if not pdf_bytes:
            raise ValueError("PDF content is empty.")

        try:
            import fitz  # PyMuPDF
        except ImportError as exc:
            raise RuntimeError("PyMuPDF is required for PDF print-format rendering.") from exc

        document = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            if document.page_count < 1:
                raise ValueError("PDF contains no pages")

            chunks: list[bytes] = [b"\x1b@"]
            for page_number in range(document.page_count):
                page = document.load_page(page_number)
                scale = self.MAX_DOTS / page.rect.width
                pixmap = page.get_pixmap(
                    matrix=fitz.Matrix(scale, scale),
                    colorspace=fitz.csGRAY,
                    alpha=False,
                )
                width = pixmap.width
                height = pixmap.height
                samples = pixmap.samples
                stride = pixmap.stride

                # Remove trailing white rows so the physical receipt ends where the
                # ERPNext print format ends instead of printing a full PDF page.
                while height > 1:
                    row_start = (height - 1) * stride
                    if any(samples[row_start + x] < self.THRESHOLD for x in range(width)):
                        break
                    height -= 1

                row_bytes = (width + 7) // 8
                data = bytearray(row_bytes * height)
                for y in range(height):
                    src = y * stride
                    dst = y * row_bytes
                    for x in range(width):
                        if samples[src + x] < self.THRESHOLD:
                            data[dst + (x // 8)] |= 0x80 >> (x % 8)

                x_l = row_bytes & 0xFF
                x_h = (row_bytes >> 8) & 0xFF
                y_l = height & 0xFF
                y_h = (height >> 8) & 0xFF
                chunks.append(b"\x1dv0\x00" + bytes((x_l, x_h, y_l, y_h)) + bytes(data))
                chunks.append(b"\n")

            chunks.append(b"\n\n\n\x1dv\x00")
            self._write_raw(printer_name, b"".join(chunks), "RB Device Agent PDF Receipt")
        finally:
            document.close()

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
        self._write_raw(printer_name, payload, "RB Device Agent Test")
