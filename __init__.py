"""Roborock robot vacuum plugin for FiestaBoard.

Strictly limited to Vestaboard Note geometry: 3 lines × 15 characters.
Attempts to show the current room name when the robot is cleaning
(supported on Saros 20 and other map-capable models).
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.plugins.base import PluginBase, PluginResult

logger = logging.getLogger(__name__)

# Short state codes that always fit in ≤8 chars
STATE_MAP = {
    1: "START",
    2: "NO DOCK",
    3: "IDLE",
    4: "REMOTE",
    5: "CLEAN",
    6: "RETURN",
    7: "MANUAL",
    8: "CHARGE",
    9: "CHG ERR",
    10: "PAUSE",
    11: "SPOT",
    12: "ERROR",
    13: "SHUTDOWN",
    14: "UPDATE",
    15: "DOCKING",
    16: "GOTO",
    17: "ZONE",
    18: "SEGMENT",
    22: "EMPTY",
    23: "WASH",
    26: "HOME",
    100: "CHARGE",
    101: "FULL",
}


def _fit(text: Any, width: int = 15) -> str:
    """Force any value into ≤ width characters (upper-cased, truncated)."""
    s = str(text or "").upper().strip()
    return s[:width]


class RobotVacuumPlugin(PluginBase):
    """Note-only Roborock status plugin (3×15) with optional room name."""

    def __init__(self, manifest: Dict[str, Any]):
        super().__init__(manifest)
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_ts: float = 0.0
        self._user_params = None
        self._device_manager = None
        self._room_map: Dict[int, str] = {}  # segment_id → name

    @property
    def plugin_id(self) -> str:
        return "robot_vacuum_cleaner"

    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        errors = []
        if not config.get("email"):
            errors.append("Roborock email is required")
        if not config.get("user_data_json"):
            errors.append("UserData JSON is required (see docs/SETUP.md)")
        else:
            try:
                json.loads(config["user_data_json"])
            except Exception:
                errors.append("user_data_json is not valid JSON")
        return errors

    def on_config_change(self, old: Dict[str, Any], new: Dict[str, Any]) -> None:
        self._cache = None
        self._user_params = None
        self._device_manager = None
        self._room_map = {}

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
            return PluginResult(available=False, error=_fit(str(e)))

    async def _resolve_room(self, device, status_trait) -> str:
        """Best-effort current room name (≤15 chars). Returns '' if unknown."""
        try:
            # 1. Try to get the current segment / room id from status
            seg_id = None
            for attr in (
                "current_segment",
                "segment",
                "in_cleaning_segment",
                "clean_segment",
                "room_id",
            ):
                val = getattr(status_trait, attr, None)
                if val is not None:
                    try:
                        seg_id = int(val)
                        break
                    except (TypeError, ValueError):
                        pass

            # 2. Load / refresh room map if we don't have it yet
            if not self._room_map and hasattr(device.v1_properties, "maps"):
                maps_trait = device.v1_properties.maps
                if maps_trait is not None:
                    await maps_trait.refresh()
                    # Common shapes across library versions
                    rooms = (
                        getattr(maps_trait, "rooms", None)
                        or getattr(maps_trait, "segments", None)
                        or []
                    )
                    for room in rooms:
                        rid = getattr(room, "segment_id", None) or getattr(
                            room, "id", None
                        )
                        rname = getattr(room, "name", None) or getattr(
                            room, "room_name", None
                        )
                        if rid is not None and rname:
                            self._room_map[int(rid)] = str(rname)

            if seg_id is not None and seg_id in self._room_map:
                return _fit(self._room_map[seg_id], 15)

            # Fallback: some firmwares expose a plain current_room string
            for attr in ("current_room", "room_name", "cleaning_room"):
                val = getattr(status_trait, attr, None)
                if val:
                    return _fit(val, 15)

        except Exception as exc:
            logger.debug("Room resolution failed: %s", exc)

        return ""

    async def _fetch_async(self) -> Dict[str, Any]:
        from roborock.data import UserData
        from roborock.devices.device_manager import UserParams, create_device_manager

        email = self.config["email"].strip()
        raw = json.loads(self.config["user_data_json"])

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
            if not getattr(d, "v1_properties", None):
                continue
            dn = (getattr(d, "name", "") or "").lower()
            if not name_filter or name_filter in dn:
                target = d
                break

        if target is None:
            raise RuntimeError("NO VACUUM FOUND")

        status_trait = target.v1_properties.status
        await status_trait.refresh()
        st = status_trait

        # --- raw values ---
        state_code = getattr(st, "state", None)
        try:
            state_int = int(state_code) if state_code is not None else -1
        except Exception:
            state_int = -1

        activity = STATE_MAP.get(state_int, "UNKNOWN")
        battery = int(
            getattr(st, "battery", None)
            or getattr(st, "battery_percent", 0)
            or 0
        )
        clean_time = getattr(st, "clean_time", 0) or 0
        clean_area = getattr(st, "clean_area", 0) or 0
        error_code = getattr(st, "error_code", 0) or 0

        # --- room (best-effort) ---
        room = await self._resolve_room(target, st)

        # --- strictly ≤15-char strings ---
        name = _fit(getattr(target, "name", None) or "ROBOROCK", 15)

        # LINE 2: activity + battery  e.g. "CLEAN  87%"
        bat_str = f"{battery}%"
        line2 = _fit(f"{activity:<7}{bat_str:>4}", 15)

        # LINE 3 priority:
        #   1. Room name (when cleaning and known)
        #   2. Area + time
        #   3. READY
        if room and activity in ("CLEAN", "ZONE", "SEGMENT", "SPOT", "PAUSE"):
            line3 = _fit(room, 15)
        else:
            area_m2 = clean_area // 1_000_000 if clean_area else 0
            mins = clean_time // 60 if clean_time else 0
            if area_m2 or mins:
                line3 = _fit(f"{area_m2}M2{mins:>6}M", 15)
            else:
                line3 = _fit("READY", 15)

        error = "OK" if not error_code else _fit(f"ERR {error_code}", 15)

        return {
            # Ready-to-use 3-line board content
            "line1": name,
            "line2": line2,
            "line3": line3,
            # Individual pieces
            "name": name,
            "activity": _fit(activity, 15),
            "battery": _fit(bat_str, 4),
            "status": _fit(activity, 15),
            "room": room or _fit("—", 15),
            "area_time": _fit(
                f"{clean_area // 1_000_000}M2 {clean_time // 60}M"
                if clean_area or clean_time
                else "—",
                15,
            ),
            "error": error,
        }


Plugin = RobotVacuumPlugin
