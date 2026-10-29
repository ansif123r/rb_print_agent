from dataclasses import dataclass

from config_store import load_config


_config = load_config()


@dataclass(frozen=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8766  # 8765 belongs to the separate offline Local POS Controller.
    app_name: str = "RB Print Agent"
    version: str = "2.0.1"
    erpnext_url: str = str(_config.get("erpnext_url", "")).strip()
    erpnext_token: str = str(_config.get("erpnext_token", "")).strip()
    erpnext_timeout: float = float(_config.get("erpnext_timeout", 15))
    poll_interval: float = float(_config.get("poll_interval", 3))
    printer_name: str = str(_config.get("printer_name", "POS80 Printer")).strip()


settings = Settings()

