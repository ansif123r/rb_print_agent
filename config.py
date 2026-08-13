from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    host: str = os.getenv("RB_AGENT_HOST", "127.0.0.1")
    port: int = int(os.getenv("RB_AGENT_PORT", "8765"))
    app_name: str = "RB Device Agent"
    version: str = "0.2.0"
    erpnext_url: str = os.getenv("RB_AGENT_ERPNEXT_URL", "").strip()
    erpnext_token: str = os.getenv("RB_AGENT_TOKEN", "").strip()
    erpnext_timeout: float = float(os.getenv("RB_AGENT_ERPNEXT_TIMEOUT", "15"))
    poll_interval: float = float(os.getenv("RB_AGENT_POLL_INTERVAL", "3"))
    printer_name: str = os.getenv("RB_AGENT_PRINTER", "POS80 Printer").strip()


settings = Settings()
