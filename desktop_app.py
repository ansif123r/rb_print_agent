from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk

import requests
import uvicorn

from config_store import is_configured, load_config, save_config

APP_NAME = "RB Print Agent"
VERSION = "1.0.1"
DEFAULT_URL = "https://rbfreshmart.m.frappe.cloud"


def configure_environment() -> None:
    data = load_config()
    os.environ["RB_AGENT_ERPNEXT_URL"] = str(data.get("erpnext_url", ""))
    os.environ["RB_AGENT_TOKEN"] = str(data.get("erpnext_token", ""))
    os.environ["RB_AGENT_PRINTER"] = str(data.get("printer_name", "POS80 Printer"))
    os.environ["RB_AGENT_ERPNEXT_TIMEOUT"] = str(data.get("erpnext_timeout", 15))
    os.environ["RB_AGENT_POLL_INTERVAL"] = str(data.get("poll_interval", 3))


def restart_application() -> None:
    executable = sys.executable
    env = os.environ.copy()

    # PyInstaller one-file applications need a clean bootloader environment
    # when the already-running executable is intentionally restarted. Without
    # this, the bootloader can reject the child process with a security
    # validation error about the parent executable path.
    if getattr(sys, "frozen", False):
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        subprocess.Popen(
            [executable],
            env=env,
            close_fds=True,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
    else:
        subprocess.Popen(
            [executable, os.path.abspath(__file__)],
            env=env,
            close_fds=True,
        )

    os._exit(0)


class SettingsWindow:
    def __init__(self, parent: tk.Tk | None = None) -> None:
        self.root = tk.Toplevel(parent) if parent else tk.Tk()
        self.root.title(f"{APP_NAME} Settings")
        self.root.geometry("560x430")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        data = load_config()
        self.url_var = tk.StringVar(value=str(data.get("erpnext_url", DEFAULT_URL)))
        self.token_var = tk.StringVar(value=str(data.get("erpnext_token", "")))
        self.printer_var = tk.StringVar(value=str(data.get("printer_name", "POS80 Printer")))
        self.status_var = tk.StringVar(value="Ready")

        frame = ttk.Frame(self.root, padding=22)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text=APP_NAME, font=("Segoe UI", 20, "bold")).pack(anchor="w")
        ttk.Label(frame, text=f"Version {VERSION} • Windows POS printing", font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 18))

        self._field(frame, "ERPNext URL", self.url_var)
        self._field(frame, "RB Print Token", self.token_var, show="*")

        ttk.Label(frame, text="Printer").pack(anchor="w", pady=(12, 4))
        row = ttk.Frame(frame)
        row.pack(fill="x")
        self.printer_combo = ttk.Combobox(row, textvariable=self.printer_var, state="readonly")
        self.printer_combo.pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Refresh", command=self.refresh_printers).pack(side="left", padx=(8, 0))

        ttk.Label(frame, textvariable=self.status_var, wraplength=500).pack(anchor="w", pady=(18, 10))

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", side="bottom")
        ttk.Button(buttons, text="Test Connection", command=self.test_connection).pack(side="left")
        ttk.Button(buttons, text="Test Printer", command=self.test_printer).pack(side="left", padx=8)
        ttk.Button(buttons, text="Save & Start", command=self.save).pack(side="right")

        self.refresh_printers()

    def _field(self, parent: ttk.Frame, label: str, variable: tk.StringVar, show: str | None = None) -> None:
        ttk.Label(parent, text=label).pack(anchor="w", pady=(8, 4))
        entry = ttk.Entry(parent, textvariable=variable, show=show or "")
        entry.pack(fill="x")

    def refresh_printers(self) -> None:
        try:
            from printer_manager import PrinterManager
            printers = PrinterManager().list_printers()
            names = [item.name for item in printers]
            self.printer_combo["values"] = names
            if names and self.printer_var.get() not in names:
                self.printer_var.set(names[0])
            self.status_var.set(f"Found {len(names)} Windows printer(s).")
        except Exception as exc:
            self.status_var.set(f"Printer discovery failed: {exc}")

    def test_connection(self) -> None:
        url = self.url_var.get().strip().rstrip("/")
        token = self.token_var.get().strip()
        printer = self.printer_var.get().strip()
        if not url or not token or not printer:
            messagebox.showwarning(APP_NAME, "ERPNext URL, token and printer are required.", parent=self.root)
            return
        try:
            response = requests.get(
                f"{url}/api/method/rbfreshmart_custom.r_b_fresh_mart_custom.rb_print.api.get_pending_jobs",
                params={"printer_name": printer, "limit": 1},
                headers={"X-RB-Print-Token": token, "Accept": "application/json"},
                timeout=15,
            )
            response.raise_for_status()
            self.status_var.set("Connection successful. ERPNext print queue is reachable.")
        except Exception as exc:
            self.status_var.set(f"Connection failed: {exc}")
            messagebox.showerror(APP_NAME, f"ERPNext connection failed:\n\n{exc}", parent=self.root)

    def test_printer(self) -> None:
        printer = self.printer_var.get().strip()
        if not printer:
            messagebox.showwarning(APP_NAME, "Select a printer first.", parent=self.root)
            return
        try:
            from print_engine import PrintEngine
            from printer_manager import PrinterManager
            if not PrinterManager().printer_exists(printer):
                raise RuntimeError(f"Printer not found: {printer}")
            PrintEngine().escpos_test_receipt(printer)
            self.status_var.set(f"Test receipt sent to {printer}.")
        except Exception as exc:
            self.status_var.set(f"Printer test failed: {exc}")
            messagebox.showerror(APP_NAME, f"Printer test failed:\n\n{exc}", parent=self.root)

    def save(self) -> None:
        url = self.url_var.get().strip().rstrip("/")
        token = self.token_var.get().strip()
        printer = self.printer_var.get().strip()
        if not url or not token or not printer:
            messagebox.showwarning(APP_NAME, "ERPNext URL, token and printer are required.", parent=self.root)
            return
        save_config(url, token, printer)
        self.status_var.set("Saved. Starting RB Print Agent...")
        self.root.after(300, restart_application)

    def close(self) -> None:
        self.root.destroy()


def start_services() -> None:
    configure_environment()
    from api import app
    from config import settings
    from queue_worker import QueueWorker

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    worker = QueueWorker()
    if settings.erpnext_url and settings.erpnext_token:
        threading.Thread(target=worker.run, name="rb-print-queue", daemon=True).start()
    else:
        logging.getLogger("rb_device_agent").warning("ERPNext queue worker disabled: agent is not configured.")

    def serve() -> None:
        uvicorn.run(app, host=settings.host, port=settings.port, log_level="warning")

    threading.Thread(target=serve, name="rb-http", daemon=True).start()


def main() -> None:
    if not is_configured():
        root = tk.Tk()
        root.withdraw()
        window = SettingsWindow(root)
        root.mainloop()
        return

    start_services()

    # Keep a small tray/settings window available without opening a console.
    try:
        import pystray
        from PIL import Image, ImageDraw

        image = Image.new("RGB", (64, 64), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((8, 8, 56, 56), outline="black", width=4)
        draw.text((19, 21), "RB", fill="black")

        def open_settings(icon: object, item: object) -> None:
            root = tk.Tk()
            root.withdraw()
            SettingsWindow(root)
            root.mainloop()

        def quit_app(icon: object, item: object) -> None:
            icon.stop()  # type: ignore[attr-defined]
            os._exit(0)

        menu = pystray.Menu(
            pystray.MenuItem("RB Print Agent Settings", open_settings),
            pystray.MenuItem("Exit", quit_app),
        )
        pystray.Icon("rb_print_agent", image, APP_NAME, menu).run()
    except Exception:
        # Tray support is optional; the print worker can continue without it.
        threading.Event().wait()


if __name__ == "__main__":
    main()
