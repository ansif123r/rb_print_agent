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

    @staticmethod
    def _content_bbox(pixmap, threshold: int = 250):
        """Return the non-white content rectangle of a grayscale pixmap."""
        width = pixmap.width
        height = pixmap.height
        samples = pixmap.samples
        stride = pixmap.stride

        left = width
        top = height
        right = -1
        bottom = -1

        for y in range(height):
            row_start = y * stride
            for x in range(width):
                if samples[row_start + x] < threshold:
                    if x < left:
                        left = x
                    if x > right:
                        right = x
                    if y < top:
                        top = y
                    if y > bottom:
                        bottom = y

        if right < left or bottom < top:
            return None

        return left, top, right + 1, bottom + 1

    def pdf(self, printer_name: str, pdf_bytes: bytes) -> None:
        """Render an ERPNext PDF print format to ESC/POS raster and print it RAW.

        ERPNext can generate a PDF page that is larger than the actual 80mm print
        format. The receipt itself may occupy only a small centered portion of an
        A4/Letter-sized PDF page. We crop the rendered page to its actual ink
        content before scaling it to the full 576-dot thermal width. This prevents
        the receipt from printing tiny in the middle of an 80mm roll.
        """
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

                # First render at a moderate scale so we can identify the actual
                # printed content rectangle without scaling a large blank PDF page.
                probe_scale = 2.0
                probe = page.get_pixmap(
                    matrix=fitz.Matrix(probe_scale, probe_scale),
                    colorspace=fitz.csGRAY,
                    alpha=False,
                )
                bbox = self._content_bbox(probe)
                if not bbox:
                    continue

                left, top, right, bottom = bbox
                crop_rect = fitz.Rect(
                    left / probe_scale,
                    top / probe_scale,
                    right / probe_scale,
                    bottom / probe_scale,
                )

                # Add a tiny safety margin so antialiased edges are not clipped.
                margin_x = min(1.0, crop_rect.width * 0.01)
                margin_y = min(1.0, crop_rect.height * 0.005)
                crop_rect = fitz.Rect(
                    max(page.rect.x0, crop_rect.x0 - margin_x),
                    max(page.rect.y0, crop_rect.y0 - margin_y),
                    min(page.rect.x1, crop_rect.x1 + margin_x),
                    min(page.rect.y1, crop_rect.y1 + margin_y),
                )

                # Scale the actual receipt content, not the surrounding PDF page,
                # to the full 80mm thermal width.
                scale = self.MAX_DOTS / crop_rect.width
                pixmap = page.get_pixmap(
                    matrix=fitz.Matrix(scale, scale),
                    colorspace=fitz.csGRAY,
                    alpha=False,
                    clip=crop_rect,
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
