from __future__ import annotations

import platform
from dataclasses import dataclass


@dataclass(frozen=True)
class PrinterInfo:
    name: str
    port: str | None = None
    driver: str | None = None
    status: int | None = None


class PrinterManager:
    """Windows printer discovery and selection helpers."""

    def __init__(self) -> None:
        if platform.system() != "Windows":
            raise RuntimeError("RB Device Agent printer support currently requires Windows.")

        try:
            import win32print  # type: ignore
        except ImportError as exc:
            raise RuntimeError("pywin32 is required for Windows printer support.") from exc

        self._win32print = win32print

    def list_printers(self) -> list[PrinterInfo]:
        flags = (
            self._win32print.PRINTER_ENUM_LOCAL
            | self._win32print.PRINTER_ENUM_CONNECTIONS
        )
        printers = self._win32print.EnumPrinters(flags, None, 4)
        result: list[PrinterInfo] = []

        for entry in printers:
            # Level 4 lists local/user connections without opening every remote device.
            name = str(entry['pPrinterName'])
            result.append(PrinterInfo(name=name))

        return sorted(result, key=lambda item: item.name.lower())

    def get_default_printer(self) -> str:
        return str(self._win32print.GetDefaultPrinter())

    def printer_exists(self, printer_name: str) -> bool:
        target = printer_name.strip().casefold()
        return any(item.name.casefold() == target for item in self.list_printers())

    def driver_name(self, printer_name: str) -> str:
        handle = self._win32print.OpenPrinter(printer_name)
        try:
            return str(self._win32print.GetPrinter(handle, 2).get('pDriverName') or '')
        finally:
            self._win32print.ClosePrinter(handle)

