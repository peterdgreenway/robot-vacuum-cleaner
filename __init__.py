"""Roborock robot vacuum plugin for FiestaBoard.

Exposes normalised, human-readable Saros 20 status fields and optional
3 x 15-character Vestaboard Note lines. Unknown values remain Unknown;
we never turn missing data into a misleading No/zero.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.plugins.base import PluginBase, PluginResult

logger = logging.getLogger(__name__)

STATE_NAMES = {
    1: "starting", 2: "not_docked", 3: "idle", 4: "remote_control",
    5: "cleaning", 6: "returning", 7: "manual", 8: "charging",
    9: "charge_error", 10: "paused", 11: "spot_cleaning", 12: "error",
    13: "shutdown", 14: "updating", 15: "docking", 16: "goto",
    17: "zone_cleaning", 18: "segment_cleaning", 22: "emptying",
    23: "washing", 26: "home", 100: "charging", 101: "fully_charged",
}

DOCK_LABELS = {
    "charging": "Charging",
    "charge": "Charging",
    "off_peak_waiting": "Delayed Charge",
    "offpeak_waiting": "Delayed Charge",
    "delayed_charge": "Delayed Charge",
    "full": "Fully Charged",
    "fully_charged": "Fully Charged",
    "charged": "Fully Charged",
}

MODE_LABELS = {
    "vac_then_mop": "Vac then Mop",
    "vacuum_then_mop": "Vac then Mop",
    "vacuum_and_mop": "Vac And Mop",
    "vac_and_mop": "Vac And Mop",
    "mop": "Mop",
    "mopping": "Mop",
    "vacuum": "Vacuum",
    "vacuuming": "Vacuum",
    "vac": "Vacuum",
    "cruise": "Cruise",
}


def _fit(value: Any, width: int = 15) -> str:
    return str(value if value is not None else "").upper().strip()[:width]


def _enum_text(value: Any) -> str:
    if value is None:
        return ""
    display = getattr(value, "display_name", None)
    if display:
        return str(display)
    raw = getattr(value, "value", None)
    if raw is not None:
        return str(raw)
    return str(value)


def _normalise_key(value: Any) -> str:
    return "_".join(str(value).strip().lower().replace("-", " ").split())


def _yes_no(value: Any) -> str:
    if value is None:
        return "Unknown"
    if isinstance(value, str):
        low = value.strip().lower()
        if low in ("true", "yes", "1", "on"):
            return "Yes"
        if low in ("false", "no", "0", "off"):
            return "No"
    if value in (True, 1):
        return "Yes"
    if value in (False, 0):
        return "No"
    return "Unknown"


def _mode_label(value: Any) -> str:
    raw = _enum_text(value)
    if not raw:
        return "Unknown"
    key = _normalise_key(raw)
    # Enum names can contain a namespace/prefix; match the most specific tail.
    for candidate, label in MODE_LABELS.items():
        if key == candidate or key.endswith("_" + candidate):
            return label
    return raw.replace("_", " ").title()


def _dock_label(value: Any) -> str:
    raw = _enum_text(value)
    if not raw:
        return "Unknown"
    key = _normalise_key(raw)
    for candidate, label in DOCK_LABELS.items():
        if key == candidate or key.endswith("_" + candidate):
            return label
    return raw.replace("_", " ").replace("-", " ").title()


def _safe_attr(obj: Any, *names: str) -> Any:
    for name in names:
        try:
            value = getattr(obj, name, None)
        except Exception:
            value = None
        if value is not None:
            return value
    return None


def _state_name(status: Any) -> str:
    state = _safe_attr(status, "state")
    if state is None:
        return "Unknown"
    display = _safe_attr(state, "display_name")
    if display:
        return str(display).lower().replace(" ", "_")
    try:
        return STATE_NAMES.get(int(state), _enum_text(state).lower())
    except (TypeError, ValueError):
        return _enum_text(state).lower().replace(" ", "_")


class RobotVacuumPlugin(PluginBase):
    """Roborock status fields for FiestaBoard and Vestaboard Note."""

    def __init__(self, manifest: Dict[str, Any]):
        super().__init__(manifest)
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_ts = 0.0

    @property
    def plugin_id(self) -> str:
        return "robot_vacuum"

    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        errors: List[str] = []
        if not config.get("email"):
            errors.append("Roborock email is required")
        raw = config.get("user_data_json")
        if not raw:
            errors.append("UserData JSON is required (see docs/SETUP.md)")
        else:
            try:
                parsed = json.loads(raw)
                if not isinstance(parsed, dict):
                    errors.append("user_data_json must contain a JSON object")
            except Exception:
                errors.append("user_data_json is not valid JSON")
        return errors

    def on_config_change(self, old: Dict[str, Any], new: Dict[str, Any]) -> None:
        self._cache = None
        self._cache_ts = 0.0

    def fetch_data(self) -> PluginResult:
        refresh = max(60, int(self.config.get("refresh_seconds", 120)))
        now = datetime.now(timezone.utc).timestamp()
        if self._cache is not None and now - self._cache_ts < refresh:
            return PluginResult(available=True, data=self._cache)
        try:
            # A fresh manager is created, used and closed inside ONE event loop.
            result = asyncio.run(self._fetch_and_close())
            self._cache = result
            self._cache_ts = now
            return PluginResult(available=True, data=result)
        except Exception as exc:
            logger.exception("Roborock fetch failed")
            if self._cache is not None:
                return PluginResult(available=True, data=self._cache)
            return PluginResult(available=False, error=_fit(str(exc)))

    async def _fetch_and_close(self) -> Dict[str, Any]:
        from roborock.data.containers import Reference, RRiot, UserData
        from roborock.devices.device_manager import UserParams, create_device_manager

        raw = json.loads(self.config["user_data_json"])
        saved_user = raw.get("user_data", raw)
        saved_rriot = saved_user.get("rriot")
        if not isinstance(saved_rriot, dict):
            raise RuntimeError("UserData JSON has no rriot credentials")
        saved_ref = saved_rriot.get("r")
        if not isinstance(saved_ref, dict):
            raise RuntimeError("UserData JSON has no rriot reference")

        # Explicit construction is required: from_dict() loses nested dataclasses
        # in the installed python-roborock version used with the Saros 20.
        reference = Reference(
            r=saved_ref.get("r"), a=saved_ref.get("a"),
            m=saved_ref.get("m"), l=saved_ref.get("l"),
        )
        rriot = RRiot(
            u=saved_rriot["u"], s=saved_rriot["s"], h=saved_rriot["h"],
            k=saved_rriot["k"], r=reference,
        )
        user_data = UserData(
            rriot=rriot, uid=saved_user.get("uid"),
            tokentype=saved_user.get("tokentype"), token=saved_user.get("token"),
            rruid=saved_user.get("rruid"), region=saved_user.get("region"),
            countrycode=saved_user.get("countrycode"), country=saved_user.get("country"),
            nickname=saved_user.get("nickname"),
            tuya_device_state=saved_user.get("tuya_device_state"),
            avatarurl=saved_user.get("avatarurl"),
        )
        params = UserParams(username=self.config["email"].strip(), user_data=user_data)
        manager = await create_device_manager(params, prefer_cache=False)
        try:
            devices = await manager.get_devices()
            name_filter = (self.config.get("device_name") or "").strip().lower()
            target = next((d for d in devices
                           if getattr(d, "v1_properties", None)
                           and (not name_filter or name_filter in (getattr(d, "name", "") or "").lower())), None)
            if target is None:
                raise RuntimeError("NO VACUUM FOUND")
            if not getattr(target, "is_connected", False):
                await target.start_connect()
            props = target.v1_properties
            status = props.status
            await status.refresh()
            return await self._normalise_data(target, status, props)
        finally:
            close_result = manager.close()
            if inspect.isawaitable(close_result):
                await close_result

    async def _normalise_data(self, device: Any, st: Any, props: Any) -> Dict[str, Any]:
        battery_raw = _safe_attr(st, "battery")
        battery = int(battery_raw) if battery_raw is not None else None
        state = _state_name(st)
        dock_raw = _safe_attr(st, "dock_state")
        dock_state = _dock_label(dock_raw)
        charging_raw = _safe_attr(st, "is_battery_charging")
        # Do not infer charging from being docked: off-peak waiting is docked, not charging.
        if charging_raw is None and state == "charging":
            charging_raw = True
        is_charging = _yes_no(charging_raw)
        dock_key = _normalise_key(_enum_text(dock_raw))
        docked = None
        if dock_key in ("off_peak_waiting", "offpeak_waiting", "charging", "full", "fully_charged", "charged"):
            docked = True
        elif state in ("not_docked", "cleaning", "returning", "manual", "remote_control", "spot_cleaning"):
            docked = False
        is_docked = _yes_no(docked)

        cleaning_mode = _mode_label(_safe_attr(st, "current_cleaning_mode_name", "current_cleaning_mode"))
        # If the current mode is not exposed, retain Unknown rather than guessing.
        activity = state.replace("_", " ").title() if state != "Unknown" else "Unknown"
        cleaning_activity = {
            "Vacuum": "Vacuuming",
            "Mop": "Mopping",
            "Vac then Mop": "Vac & Mop",
            "Vac And Mop": "Vac & Mop",
            "Cruise": "Cruise",
        }.get(cleaning_mode, "Unknown")
        room = await self._resolve_room(props, st)
        error_raw = _safe_attr(st, "error_code")
        error_name = _safe_attr(st, "error_code_name")
        error = "None" if error_raw in (None, 0) or str(error_name).lower() in ("none", "ok", "no error") else str(error_name or _enum_text(error_raw))
        clean_time_seconds = _safe_attr(st, "clean_time")
        clean_area_raw = _safe_attr(st, "square_meter_clean_area")
        if clean_area_raw is None:
            raw_area = _safe_attr(st, "clean_area")
            clean_area_raw = round(float(raw_area) / 1_000_000, 1) if raw_area is not None else None
        progress = _safe_attr(st, "clean_percent")
        dnd = _yes_no(_safe_attr(st, "dnd_enabled"))
        map_present = _yes_no(_safe_attr(st, "map_present"))
        name = str(getattr(device, "name", None) or "Roborock")

        # Individual fields are deliberately not truncated; FiestaBoard can use them
        # in any template. The three optional Note lines are capped at 15 chars.
        line1 = _fit(f"{name} - {battery}%" if battery is not None else name)
        if state in ("cleaning", "zone_cleaning", "segment_cleaning", "spot_cleaning"):
            display_activity = cleaning_activity if cleaning_activity != "Unknown" else "Cleaning"
            line2_text = display_activity
            line3_text = room
        else:
            line2_text = dock_state if dock_state != "Unknown" else activity
            line3_text = f"CHARGING {is_charging.upper()}" if is_charging != "Unknown" else activity
        return {
            "name": name,
            "battery_level": battery if battery is not None else "Unknown",
            "battery": f"{battery}%" if battery is not None else "Unknown",
            "is_charging": is_charging,
            "is_docked": is_docked,
            "dock_state": dock_state,
            "robot_state": state,
            "activity": activity,
            "cleaning_activity": cleaning_activity,
            "current_room": room,
            "room": room,
            "cleaning_mode": cleaning_mode,
            "cleaning_progress": progress if progress is not None else "Unknown",
            "cleaning_time_minutes": round(float(clean_time_seconds) / 60, 1) if clean_time_seconds is not None else "Unknown",
            "area_cleaned_m2": clean_area_raw if clean_area_raw is not None else "Unknown",
            "do_not_disturb": dnd,
            "map_present": map_present,
            "error": error,
            "has_error": "No" if error == "None" else "Yes",
            "line1": line1,
            "line2": _fit(line2_text),
            "line3": _fit(line3_text),
            # Compatibility with the original plugin's variable names.
            "status": activity,
            "area_time": _fit(f"{clean_area_raw}M2 {round(float(clean_time_seconds or 0)/60)}M" if clean_area_raw is not None else "Unknown"),
        }

    async def _resolve_room(self, props: Any, status: Any) -> str:
        """Resolve room only when a current segment can be matched to a map room."""
        # Status/current-position properties differ across Roborock firmware versions.
        segment_id = None
        for obj in (status, props):
            for attr in ("current_segment", "current_segment_id", "segment", "in_cleaning_segment", "clean_segment", "room_id"):
                value = _safe_attr(obj, attr)
                if value is not None:
                    try:
                        segment_id = int(value)
                        break
                    except (TypeError, ValueError):
                        continue
            if segment_id is not None:
                break

        room_sources = []
        for trait_name in ("rooms", "maps", "home"):
            trait = _safe_attr(props, trait_name)
            if trait is None:
                continue
            room_sources.append(trait)
            refresh = _safe_attr(trait, "refresh")
            if callable(refresh):
                try:
                    await refresh()
                except Exception as exc:
                    logger.debug("Could not refresh %s trait: %s", trait_name, exc)
            for attr in ("rooms", "segments", "room_list", "current_map"):
                value = _safe_attr(trait, attr)
                if value is not None:
                    room_sources.append(value)

        def walk(value: Any, depth: int = 0):
            if depth > 4 or value is None:
                return
            if isinstance(value, dict):
                yield value
                for child in value.values():
                    yield from walk(child, depth + 1)
            elif isinstance(value, (list, tuple, set)):
                for child in value:
                    yield from walk(child, depth + 1)
            else:
                rid = _safe_attr(value, "segment_id", "id", "room_id")
                rname = _safe_attr(value, "name", "room_name")
                if rid is not None and rname:
                    yield {"id": rid, "name": rname}
                for attr in ("rooms", "segments", "room_list", "data", "current_map"):
                    child = _safe_attr(value, attr)
                    if child is not None and child is not value:
                        yield from walk(child, depth + 1)

        if segment_id is not None:
            for source in room_sources:
                for room in walk(source):
                    rid = room.get("segment_id", room.get("id", room.get("room_id")))
                    rname = room.get("name", room.get("room_name"))
                    try:
                        if int(rid) == segment_id and rname:
                            return str(rname)
                    except (TypeError, ValueError):
                        pass
        # Some library/firmware versions expose a direct current-room string.
        for obj in (status, props):
            direct = _safe_attr(obj, "current_room", "room_name", "cleaning_room")
            if isinstance(direct, str) and direct.strip():
                return direct.strip()
        return "Unknown"
