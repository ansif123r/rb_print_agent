from dataclasses import dataclass

from config_store import load_config


_config = load_config()


@dataclass(frozen=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8765
    app_name: str = "RB Print Agent"
    version: str = "0.3.1"
    erpnext_url: str = str(_config.get("erpnext_url", "")).strip()
    erpnext_token: str = str(_config.get("erpnext_token", "")).strip()
    erpnext_timeout: float = float(_config.get("erpnext_timeout", 15))
    # Keep the queue responsive even when an older config.json still contains
    # the previous 3-second polling value.
    poll_interval: float = min(max(float(_config.get("poll_interval", 0.75)), 0.25), 0.75)
    printer_name: str = str(_config.get("printer_name", "POS80 Printer")).strip()


settings = Settings()
