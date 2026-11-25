"""Roborock robot vacuum plugin for FiestaBoard – direct cloud API.

Exposes live status, battery, fan speed, clean statistics and consumable
levels from any Roborock vacuum that supports the V1 Properties API.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.plugins.base import PluginBase, PluginResult

logger = logging.getLogger(__name__)

# Common Roborock state codes → short human-readable strings
STATE_MAP = {
    1: "Starting",
    2: "Charger disc.",
    3: "Idle",
    4: "Remote",
    5: "Cleaning",
    6: "Returning",
    7: "Manual",
    8: "Charging",
    9: "Charging err",
    10: "Paused",
    11: "Spot",
    12: "Error",
    13: "Shutting down",
    14: "Updating",
    15: "Docking",
    16: "Goto",
    17: "Zoned",
    18: "Segment",
    22: "Emptying",
    23: "Washing",
    26: "Going home",
    100: "Charging",
    101: "Fully charged",
}


class RobotVacuumPlugin(PluginBase):
    """Fetch live data from a Roborock vacuum via the official cloud API."""

    def __init__(self, manifest: Dict[str, Any]):
        super().__init__(manifest)
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_ts: float = 0.0
        self._user_params = None
        self._device_manager = None

    @property
    def plugin_id(self) -> str:
        return "robot_vacuum"

    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        errors = []
        if not config.get("email"):
            errors.append("Roborock account email is required")
        if not config.get("user_data_json"):
            errors.append(
                "UserData JSON is required (see docs/SETUP.md for how to obtain it)"
            )
        else:
            try:
                json.loads(config["user_data_json"])
            except Exception:
                errors.append("user_data_json is not valid JSON")
        return errors

    def on_config_change(self, old: Dict[str, Any], new: Dict[str, Any]) -> None:
        """Clear cached session when credentials change."""
        self._cache = None
        self._user_params = None
        self._device_manager = None

    def fetch_data(self) -> PluginResult:
        refresh = int(self.config.get("refresh_seconds", 120))
        now = datetime.now(timezone.utc).timestamp()
        if self._cache and (now - self._cache_ts) < refresh:
            return PluginResult(available=True, data=self._cache)

        try:
            data = asyncio.run(self._fetch_async())
            self._cache = data
            self._cache_ts = now
            return PluginResult(available=True, data=data)
        except Exception as e:
            logger.exception("Roborock fetch failed")
            if self._cache:
                return PluginResult(available=True, data=self._cache)
            return PluginResult(available=False, error=str(e))

    async def _fetch_async(self) -> Dict[str, Any]:
        from roborock.data import UserData
        from roborock.devices.device_manager import UserParams, create_device_manager

        email = self.config["email"].strip()
        raw = json.loads(self.config["user_data_json"])

        # Reconstruct the official UserData object (handles both old & new library shapes)
        if hasattr(UserData, "from_dict"):
            user_data = UserData.from_dict(raw)
        else:
            user_data = UserData(**raw)

        if self._user_params is None:
            self._user_params = UserParams(username=email, user_data=user_data)

        if self._device_manager is None:
            self._device_manager = await create_device_manager(self._user_params)

        devices = await self._device_manager.get_devices()
        name_filter = (self.config.get("device_name") or "").strip().lower()

        target = None
        for d in devices:
            # Prefer classic V1 protocol vacuums (S7 / S8 / Q-series, etc.)
            if not getattr(d, "v1_properties", None):
                continue
            dn = (getattr(d, "name", "") or "").lower()
            if not name_filter or name_filter in dn:
                target = d
                break

        if target is None:
            raise RuntimeError(
                "No matching Roborock vacuum with v1_properties found on this account"
            )

        # Refresh live status
        status_trait = target.v1_properties.status
        await status_trait.refresh()

        # Optional consumables (not present on every model / firmware)
        consumables: Dict[str, Any] = {}
        if (
            hasattr(target.v1_properties, "consumables")
            and target.v1_properties.consumables
        ):
            cons = target.v1_properties.consumables
            await cons.refresh()
            consumables = {
                "main_brush": getattr(cons, "main_brush_work_time", None),
                "side_brush": getattr(cons, "side_brush_work_time", None),
                "filter": getattr(cons, "filter_work_time", None),
                "sensor": getattr(cons, "sensor_dirty_time", None),
            }

        st = status_trait
        state_code = getattr(st, "state", None)
        try:
            state_int = int(state_code) if state_code is not None else -1
        except Exception:
            state_int = -1
        status_str = STATE_MAP.get(state_int, str(state_code or "Unknown"))

        battery = (
            getattr(st, "battery", None)
            or getattr(st, "battery_percent", 0)
            or 0
        )
        fan = str(
            getattr(st, "fan_power", None)
            or getattr(st, "fan_speed", "")
            or ""
        )
        clean_time = getattr(st, "clean_time", 0) or 0  # seconds
        clean_area = getattr(st, "clean_area", 0) or 0  # mm²
        error_code = getattr(st, "error_code", 0) or 0

        def pct(hours_left: Any, total: int = 300) -> str:
            if hours_left is None:
                return "—"
            try:
                return f"{max(0, min(100, int(100 * hours_left / total)))}%"
            except Exception:
                return "—"

        activity = (
            "DOCKED"
            if status_str.lower()
            in ("charging", "fully charged", "idle", "docking")
            else "CLEANING"
            if "clean" in status_str.lower()
            else "RETURNING"
            if any(x in status_str.lower() for x in ("return", "home", "dock"))
            else "PAUSED"
            if "pause" in status_str.lower()
            else status_str.upper()[:12]
        )

        battery_icon = (
            "FULL"
            if battery >= 80
            else "HIGH"
            if battery >= 50
            else "LOW"
            if battery >= 20
            else "CRIT"
        )

        # Compact line that fits a Vestaboard Note (15 characters)
        formatted = f"{activity[:8]:<8}{battery:>3}%"

        return {
            "name": (getattr(target, "name", None) or "Roborock")[:15],
            "status": status_str[:15],
            "activity": activity,
            "battery": f"{battery}%",
            "battery_icon": battery_icon,
            "fan_speed": fan[:10],
            "clean_time": f"{clean_time // 60}m" if clean_time else "—",
            "clean_area": f"{clean_area // 1_000_000}m2" if clean_area else "—",
            "error": "OK" if not error_code else f"ERR {error_code}",
            "docked": str(activity in ("DOCKED", "CHARGING")).lower(),
            "charging": str("charg" in status_str.lower()).lower(),
            "cleaning": str(activity == "CLEANING").lower(),
            "mop_attached": str(
                getattr(st, "water_box_status", 0) not in (0, None)
            ).lower(),
            "main_brush": pct(consumables.get("main_brush")),
            "side_brush": pct(consumables.get("side_brush")),
            "filter": pct(consumables.get("filter")),
            "sensor": pct(consumables.get("sensor"), 30),
            "formatted": formatted,
            "last_updated": datetime.now(timezone.utc).strftime("%H:%M"),
        }


Plugin = RobotVacuumPlugin
