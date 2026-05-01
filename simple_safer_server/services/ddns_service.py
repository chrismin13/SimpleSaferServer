import json
from contextlib import suppress
from typing import Any, Dict


class DdnsService:
    """Coordinates DDNS page configuration without depending on Flask route state."""

    def __init__(self, runtime: Any, config_manager: Any, task_service: Any, logger: Any) -> None:
        self._runtime = runtime
        self._config_manager = config_manager
        self._task_service = task_service
        self._logger = logger

    def get_config_payload(self) -> Dict[str, Any]:
        status = self._read_status()
        ddns_task = self._task_service.get_task("DDNS Update")
        next_run = ddns_task.next_run if ddns_task else "Unknown"
        return {
            "success": True,
            "config": {
                "duckdns": {
                    "enabled": self._config_manager.get_value("ddns", "duckdns_enabled", "false")
                    == "true",
                    "domain": self._config_manager.get_value("ddns", "duckdns_domain", ""),
                    # DDNS settings are credential editors for trusted admins, so
                    # return the stored token to keep the UI useful for audits.
                    "token": self._config_manager.get_secret("duckdns_token", ""),
                    "token_present": self._config_manager.get_secret("duckdns_token", "") != "",
                },
                "cloudflare": {
                    "enabled": self._config_manager.get_value("ddns", "cloudflare_enabled", "false")
                    == "true",
                    "zone": self._config_manager.get_value("ddns", "cloudflare_zone", ""),
                    "record": self._config_manager.get_value("ddns", "cloudflare_record", ""),
                    "token": self._config_manager.get_secret("cloudflare_token", ""),
                    "token_present": self._config_manager.get_secret("cloudflare_token", "") != "",
                    "proxy": self._config_manager.get_value("ddns", "cloudflare_proxy", "false")
                    == "true",
                },
            },
            "status": status,
            "next_run": next_run,
        }

    def save_config(self, data: Dict[str, Any]) -> str:
        if "duckdns" in data:
            if not isinstance(data["duckdns"], dict):
                raise ValueError("duckdns settings must be a JSON object")
            self._save_duckdns(data["duckdns"])
        if "cloudflare" in data:
            if not isinstance(data["cloudflare"], dict):
                raise ValueError("cloudflare settings must be a JSON object")
            self._save_cloudflare(data["cloudflare"])

        if self._trigger_sync():
            return "DDNS configuration saved and update triggered."
        return (
            "DDNS configuration saved. Immediate sync could not be triggered "
            "— the next scheduled run will use the new config."
        )

    def run_manual(self) -> str:
        task = self._task_service.get_task("DDNS Update")
        if not task:
            raise LookupError("DDNS Update task not found")
        task.start()
        return "DDNS sync started successfully."

    def _read_status(self) -> Dict[str, Any]:
        status_file = self._runtime.volatile_dir / "ddns_status.json"
        if not status_file.exists():
            return {}
        with suppress(Exception):
            status = json.loads(status_file.read_text())
            if isinstance(status, dict):
                return status
        return {}

    def _save_duckdns(self, duckdns: Dict[str, Any]) -> None:
        domain = duckdns.get("domain", "").strip()
        token = duckdns.get("token", "").strip()
        enabled = _coerce_bool(duckdns.get("enabled", False))

        if enabled:
            # A stored duckdns_token from get_secret lets admins update DuckDNS
            # settings without re-entering the token; store_secret only runs
            # when this request includes a replacement token.
            existing_token = self._config_manager.get_secret("duckdns_token")
            if not domain:
                raise ValueError("DuckDNS domain is required when enabled")
            if not token and not existing_token:
                raise ValueError("DuckDNS token is required when enabled")

        self._config_manager.set_value("ddns", "duckdns_domain", domain)
        self._config_manager.set_value("ddns", "duckdns_enabled", str(enabled).lower())
        if token:
            self._config_manager.store_secret("duckdns_token", token)

    def _save_cloudflare(self, cloudflare: Dict[str, Any]) -> None:
        zone = cloudflare.get("zone", "").strip()
        record = cloudflare.get("record", "").strip()
        token = cloudflare.get("token", "").strip()
        proxy = _coerce_bool(cloudflare.get("proxy", False))
        enabled = _coerce_bool(cloudflare.get("enabled", False))

        if enabled:
            existing_token = self._config_manager.get_secret("cloudflare_token")
            if not zone:
                raise ValueError("Cloudflare zone is required when enabled")
            if not record:
                raise ValueError("Cloudflare record is required when enabled")
            if not token and not existing_token:
                raise ValueError("Cloudflare token is required when enabled")

        self._config_manager.set_value("ddns", "cloudflare_zone", zone)
        self._config_manager.set_value("ddns", "cloudflare_record", record)
        self._config_manager.set_value("ddns", "cloudflare_proxy", str(proxy).lower())
        self._config_manager.set_value("ddns", "cloudflare_enabled", str(enabled).lower())
        if token:
            self._config_manager.store_secret("cloudflare_token", token)

    def _trigger_sync(self) -> bool:
        try:
            task = self._task_service.get_task("DDNS Update")
            if not task:
                return False
            task.start()
            return True
        except Exception:
            self._logger.warning(
                "Could not trigger immediate DDNS sync; config was saved successfully",
                exc_info=True,
            )
            return False


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}
