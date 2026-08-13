from __future__ import annotations

import logging
from typing import Any

import requests

from config import settings

logger = logging.getLogger("rb_device_agent.erpnext")


class ERPNextClient:
    def __init__(self) -> None:
        if not settings.erpnext_url or not settings.erpnext_token:
            raise RuntimeError("ERPNext URL and RB_AGENT_TOKEN must be configured.")
        self.base_url = settings.erpnext_url.rstrip("/")
        self.headers = {
            "X-RB-Print-Token": settings.erpnext_token,
            "Accept": "application/json",
        }
        self.timeout = settings.erpnext_timeout

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = requests.request(
            method,
            f"{self.base_url}{path}",
            headers=self.headers,
            timeout=self.timeout,
            **kwargs,
        )
        response.raise_for_status()
        body = response.json()
        return body.get("message", body)

    def get_pending_jobs(self, printer_name: str, limit: int = 10) -> list[dict[str, Any]]:
        result = self._request(
            "GET",
            "/api/method/rbfreshmart_custom.r_b_fresh_mart_custom.rb_print.api.get_pending_jobs",
            params={"printer_name": printer_name, "limit": limit},
        )
        return result or []

    def update_job_status(self, job_name: str, status: str, error_message: str | None = None) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/method/rbfreshmart_custom.r_b_fresh_mart_custom.rb_print.api.update_job_status",
            json={
                "job_name": job_name,
                "status": status,
                "error_message": error_message,
            },
        )
