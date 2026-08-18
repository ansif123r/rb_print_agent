from __future__ import annotations

import base64
import platform


class PrintEngine:
    """Windows RAW printer output with ESC/POS and ERPNext PDF raster support."""

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
    def _content_bbox(pixmap, threshold: int = 250):
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
                    left = min(left, x)
                    right = max(right, x)
                    top = min(top, y)
                    bottom = max(bottom, y)

        if right < left or bottom < top:
            return None

        return left, top, right + 1, bottom + 1

    @staticmethod
    def _mono_raster_rows(pix) -> bytes:
        width = pix.width
        height = pix.height
        channels = pix.n
        samples = pix.samples
        stride = pix.stride
        row_bytes = (width + 7) // 8
        output = bytearray(row_bytes * height)

        for y in range(height):
            src_row = y * stride
            dst_row = y * row_bytes
            for x in range(width):
                offset = src_row + x * channels
                r = samples[offset]
                g = samples[offset + 1]
                b = samples[offset + 2]
                gray = (299 * r + 587 * g + 114 * b) // 1000
                if gray < self.THRESHOLD:
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

    def pdf_bytes_to_escpos(self, pdf_bytes: bytes, target_width: int = MAX_DOTS) -> bytes:
        """Render the actual Print Format content to the full 80mm thermal width.

        ERPNext may render an 80mm Print Format inside a larger PDF page. Scaling
        the whole PDF page to 576 dots makes the receipt tiny. We first find the
        non-white content rectangle, crop to it, and then scale that rectangle to
        the full thermal width.
        """
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

                # Probe the page to locate the actual receipt content. This removes
                # the large blank margins from an A4/Letter-sized PDF wrapper.
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
                crop = fitz.Rect(
                    left / probe_scale,
                    top / probe_scale,
                    right / probe_scale,
                    bottom / probe_scale,
                )

                # Small margin to avoid clipping antialiased edges.
                margin_x = min(1.0, crop.width * 0.01)
                margin_y = min(1.0, crop.height * 0.005)
                crop = fitz.Rect(
                    max(page.rect.x0, crop.x0 - margin_x),
                    max(page.rect.y0, crop.y0 - margin_y),
                    min(page.rect.x1, crop.x1 + margin_x),
                    min(page.rect.y1, crop.y1 + margin_y),
                )

                scale = target_width / crop.width
                pix = page.get_pixmap(
                    matrix=fitz.Matrix(scale, scale),
                    colorspace=fitz.csRGB,
                    alpha=False,
                    clip=crop,
                )

                # Remove trailing white rows. This preserves the compact receipt
                # height instead of feeding the blank remainder of the PDF page.
                height = pix.height
                samples = pix.samples
                stride = pix.stride
                while height > 1:
                    row_start = (height - 1) * stride
                    if any(
                        ((299 * samples[row_start + x * 3]
                          + 587 * samples[row_start + x * 3 + 1]
                          + 114 * samples[row_start + x * 3 + 2]) // 1000) < self.THRESHOLD
                        for x in range(pix.width)
                    ):
                        break
                    height -= 1

                if height != pix.height:
                    # Re-render with the cropped height so the raster payload is
                    # exactly the receipt content that needs to be printed.
                    crop2 = fitz.Rect(crop.x0, crop.y0, crop.x1, crop.y0 + height / scale)
                    pix = page.get_pixmap(
                        matrix=fitz.Matrix(scale, scale),
                        colorspace=fitz.csRGB,
                        alpha=False,
                        clip=crop2,
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
