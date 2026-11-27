"""FiestaBoard data plugin for the Roborock service.

The companion service owns Roborock authentication, polling and usage control.
This plugin only reads the service API and synchronises the requested schedule.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List
from urllib.parse import urljoin

from src.plugins.base import PluginBase, PluginResult

logger = logging.getLogger(__name__)


def _text(value: Any, default: str = "Unknown") -> str:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def _fit(value: Any, width: int = 15) -> str:
    return _text(value, "").upper().strip()[:width]


class RobotVacuumPlugin(PluginBase):
    """Read Roborock status from the companion service."""

    def __init__(self, manifest: Dict[str, Any]):
        super().__init__(manifest)
        self._cache: Dict[str, Any] = {}
        self._cache_ts = 0.0

    @property
    def plugin_id(self) -> str:
        return "robot_vacuum"

    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        errors: List[str] = []
        base = str(config.get("service_url", "")).strip().rstrip("/")
        if not base.startswith(("http://", "https://")):
            errors.append("Service URL must begin with http:// or https://")
        try:
            interval = int(config.get("polling_interval_seconds", 60))
            if interval < 30 or interval > 3600:
                errors.append("Polling interval must be between 30 and 3600 seconds")
        except (TypeError, ValueError):
            errors.append("Polling interval must be a number")
        return errors

    def on_config_change(self, old: Dict[str, Any], new: Dict[str, Any]) -> None:
        self._cache = {}
        self._cache_ts = 0.0

    def _request(self, path: str, method: str = "GET", payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        base = str(self.config.get("service_url", "http://192.168.100.99:8088")).rstrip("/") + "/"
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            urljoin(base, path.lstrip("/")), data=data, method=method,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=8) as response:
            raw = response.read().decode("utf-8")
        parsed = json.loads(raw) if raw else {}
        if not isinstance(parsed, dict):
            raise RuntimeError("Roborock service returned an unexpected response")
        return parsed

    def refresh_now(self) -> Dict[str, Any]:
        """Callable helper for integrations that can invoke plugin methods.

        FiestaBoard's documented data-plugin contract does not expose this as a
        native settings-page button. Use the service dashboard's Refresh Now.
        """
        return self._request("/refresh", method="POST", payload={})

    def fetch_data(self) -> PluginResult:
        try:
            interval = max(30, int(self.config.get("polling_interval_seconds", 60)))
            now = datetime.now(timezone.utc).timestamp()
            if self._cache and now - self._cache_ts < interval:
                return PluginResult(available=True, data=self._cache)

            # The service remains the sole authority for polling and API budget.
            # FiestaBoard sends desired schedule values; the service enforces them.
            schedule = {
                "polling_start": str(self.config.get("polling_start", "07:15")),
                "polling_end": str(self.config.get("polling_end", "21:00")),
                "polling_interval_seconds": interval,
                "daily_operation_limit": max(1, int(self.config.get("daily_operation_limit", 1000))),
            }
            try:
                self._request("/config", method="PUT", payload=schedule)
            except Exception as exc:
                logger.warning("Could not synchronise Roborock service settings: %s", exc)

            status = self._request("/status")
            data = dict(status.get("data", status))
            data.setdefault("last_refresh", data.get("last_updated", "Unknown"))
            data.setdefault("polling_start", schedule["polling_start"])
            data.setdefault("polling_end", schedule["polling_end"])
            data.setdefault("polling_interval_seconds", interval)
            data.setdefault("daily_operation_limit", schedule["daily_operation_limit"])

            battery = data.get("battery_level", data.get("battery", "Unknown"))
            if isinstance(battery, str) and battery.endswith("%"):
                battery = battery[:-1]
            data["battery_level"] = battery
            data["battery"] = f"{battery}%" if str(battery).isdigit() else _text(data.get("battery"), "Unknown")
            for key in ("is_charging", "is_docked", "do_not_disturb", "map_present", "has_error"):
                data[key] = _text(data.get(key))
            data["current_room"] = _text(data.get("current_room", data.get("room")))
            data["room"] = data["current_room"]
            data["activity"] = _text(data.get("activity", data.get("cleaning_activity")))
            data["cleaning_activity"] = _text(data.get("cleaning_activity", data.get("activity")))
            data["cleaning_mode"] = _text(data.get("cleaning_mode"))
            data["dock_state"] = _text(data.get("dock_state"))
            data["error"] = _text(data.get("error"), "None")
            data["name"] = _text(data.get("name"), "Roborock")
            data["line1"] = _fit(f"{data['name']} {data['battery']}")
            data["line2"] = _fit(data["activity"])
            data["line3"] = _fit(data["current_room"])
            self._cache = data
            self._cache_ts = now
            return PluginResult(available=True, data=data)
        except (urllib.error.URLError, TimeoutError, ValueError, RuntimeError, KeyError) as exc:
            logger.exception("Roborock service fetch failed")
            if self._cache:
                return PluginResult(available=True, data=self._cache)
            return PluginResult(available=False, error=str(exc)[:120])
        except Exception as exc:
            logger.exception("Unexpected Roborock plugin error")
            if self._cache:
                return PluginResult(available=True, data=self._cache)
            return PluginResult(available=False, error=str(exc)[:120])
