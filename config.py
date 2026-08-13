from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    host: str = os.getenv("RB_AGENT_HOST", "127.0.0.1")
    port: int = int(os.getenv("RB_AGENT_PORT", "8765"))
    app_name: str = "RB Device Agent"
    version: str = "0.1.0"


settings = Settings()
