from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import asdict, is_dataclass
from enum import Enum
from contextlib import asynccontextmanager
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from roborock.data.containers import UserData, RRiot, Reference
from roborock.roborock_typing import RoborockCommand
from roborock.devices.device_manager import UserParams, create_device_manager

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("roborock-service")

DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
CREDENTIALS_FILE = Path(os.getenv("CREDENTIALS_FILE", "/credentials/roborock_credentials.json"))
CONFIG_FILE = DATA_DIR / "config.json"
USAGE_FILE = DATA_DIR / "api_usage.json"
TZ = ZoneInfo("Europe/London")

DEFAULT_CONFIG = {
    "night_start": "03:00", "night_end": "04:00", "night_interval_seconds": 900,
    "peak_start": "07:30", "peak_end": "10:30", "peak_interval_seconds": 600,
    "default_interval_seconds": 3600, "daily_operation_limit": 1000,
    "slowdown_percent": 80, "stop_percent": 90,
}
state: dict[str, Any] = {
    "manager": None, "device": None, "status": None,
    "data": {"available": False, "name": "Roborock Saros 20", "error": "Waiting for credentials"},
    "last_error": None, "last_refresh": None, "refresh_lock": asyncio.Lock(),
    "scheduler_task": None, "usage": {},
}


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2), encoding="utf-8")
    tmp.replace(path)


def config() -> dict[str, Any]:
    saved = read_json(CONFIG_FILE, {})
    return {**DEFAULT_CONFIG, **(saved if isinstance(saved, dict) else {})}


def today_key() -> str:
    return datetime.now(TZ).date().isoformat()


def usage() -> dict[str, Any]:
    saved = read_json(USAGE_FILE, {})
    if not isinstance(saved, dict) or saved.get("date") != today_key():
        saved = {"date": today_key(), "tracked_operations": 0}
    state["usage"] = saved
    return saved


def enum_text(value: Any, default: str = "Unknown") -> str:
    if value is None:
        return default
    return str(getattr(value, "display_name", getattr(value, "value", value)))


def number(value: Any, default: float = 0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

def seconds_value(value: Any) -> float | None:
    if value is None:
        return None
    if hasattr(value, "total_seconds"):
        try:
            return float(value.total_seconds())
        except (TypeError, ValueError):
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def format_duration(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "Unknown"
    total = int(round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes = remainder // 60
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def diagnostic_value(value: Any) -> Any:
    """Convert library objects into JSON-safe diagnostic data."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return diagnostic_value(value.value)
    if is_dataclass(value):
        return diagnostic_value(asdict(value))
    if isinstance(value, dict):
        return {str(key): diagnostic_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [diagnostic_value(item) for item in value]
    if hasattr(value, "__dict__"):
        return {
            key: diagnostic_value(item)
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
    return str(value)


def build_user_params(raw: dict[str, Any]) -> UserParams:
    account = raw["account"]
    saved_user = raw["user_data"]
    saved_rriot = saved_user["rriot"]
    saved_reference = saved_rriot["r"]
    reference = Reference(
        r=saved_reference.get("r"), a=saved_reference.get("a"),
        m=saved_reference.get("m"), l=saved_reference.get("l"),
    )
    rriot = RRiot(
        u=saved_rriot["u"], s=saved_rriot["s"], h=saved_rriot["h"],
        k=saved_rriot["k"], r=reference,
    )
    user_data = UserData(
        rriot=rriot,
        uid=saved_user.get("uid"), tokentype=saved_user.get("tokentype"),
        token=saved_user.get("token"), rruid=saved_user.get("rruid"),
        region=saved_user.get("region"), countrycode=saved_user.get("countrycode"),
        country=saved_user.get("country"), nickname=saved_user.get("nickname"),
        tuya_device_state=saved_user.get("tuya_device_state"),
        avatarurl=saved_user.get("avatarurl"),
    )
    return UserParams(username=account["email"], user_data=user_data)


async def connect_device() -> None:
    if not CREDENTIALS_FILE.exists():
        raise FileNotFoundError(f"Credentials file not found: {CREDENTIALS_FILE}")
    raw = json.loads(CREDENTIALS_FILE.read_text(encoding="utf-8"))
    params = build_user_params(raw)
    manager = await create_device_manager(params, prefer_cache=False)
    devices = await manager.get_devices()
    if not devices:
        raise RuntimeError("Roborock account returned no devices")
    device = next((d for d in devices if "Saros 20" in str(getattr(d, "name", ""))), devices[0])
    if state["manager"] is not None:
        try:
            await state["manager"].close()
        except Exception:
            log.exception("Error closing previous device manager")
    state["manager"] = manager
    state["device"] = device
    state["status"] = device.v1_properties.status
    log.info("Connected to device: %s", getattr(device, "name", "Roborock"))


def current_status_data(status: Any, device: Any, current_room: str = "Unknown") -> dict[str, Any]:
    state_value = getattr(status, "state", None)
    charge_value = getattr(status, "charge_status", None)
    cleaning_value = getattr(status, "in_cleaning", None)
    battery = getattr(status, "battery", None)
    raw_clean_area = getattr(status, "clean_area", None)
    session_area_m2 = getattr(status, "square_meter_clean_area", None)
    if session_area_m2 is None and raw_clean_area is not None:
        session_area_m2 = number(raw_clean_area) / 1000000
    clean_time_seconds = seconds_value(getattr(status, "clean_time", None))
    clean_summary = getattr(getattr(device, "v1_properties", None), "clean_summary", None)
    total_time_seconds = seconds_value(getattr(clean_summary, "clean_time", None))
    total_area_m2 = getattr(clean_summary, "square_meter_clean_area", None)
    if total_area_m2 is not None:
        total_area_m2 = number(total_area_m2)
    total_clean_count = getattr(clean_summary, "clean_count", None)
    clean_records = getattr(clean_summary, "records", None) or []
    clean_timestamps = [number(record, -1) for record in clean_records]
    clean_timestamps = [stamp for stamp in clean_timestamps if stamp > 0]
    last_clean_run = (
        datetime.fromtimestamp(max(clean_timestamps), TZ).isoformat(timespec="seconds")
        if clean_timestamps else "Unknown"
    )
    clean_percent = getattr(status, "clean_percent", None)
    returning = getattr(status, "in_returning", None)
    error_value = getattr(status, "error_code", None)
    dock_error = getattr(status, "dock_error_status", None)
    dock_type = getattr(status, "dock_type", None)
    map_present = getattr(status, "map_present", None)
    mode = getattr(status, "current_cleaning_mode", None)

    state_name = enum_text(state_value)
    cleaning_name = enum_text(cleaning_value)
    charge_name = enum_text(charge_value)
    # Off-peak waiting is docked but deliberately not charging.
    # On this Saros 20, state=charging with charge_status=0 and a battery
    # below 100% is the scheduled off-peak waiting condition observed by the
    # user. It is docked, but deliberately not drawing charge.
    charge_raw = getattr(charge_value, "value", charge_value)
    if "off_peak" in state_name.lower() or "waiting" in state_name.lower() or (state_name.lower() == "charging" and charge_raw in (0, "0") and battery is not None and battery < 100):
        dock_state = "Delayed Charge"
        charging = False
        is_docked = True
    elif battery == 100 and "charging" in state_name.lower():
        dock_state = "Fully Charged"
        charging = False
        is_docked = True
    elif "charging" in state_name.lower():
        dock_state = "Charging"
        charging = True
        is_docked = True
    else:
        dock_state = state_name
        charging = False
        is_docked = any(x in state_name.lower() for x in ("docked", "waiting", "idle"))

    mode_text = enum_text(mode)
    if mode_text == "Unknown":
        mode_text = "Unknown"

    return {
        "available": True,
        "name": str(getattr(device, "name", "Roborock")),
        "robot_state": state_name,
        "state": state_name,
        "battery_level": battery if battery is not None else "Unknown",
        "battery": f"{battery}%" if battery is not None else "Unknown",
        "is_charging": "Yes" if charging else ("No" if state_value is not None else "Unknown"),
        "is_docked": "Yes" if is_docked else ("No" if state_value is not None else "Unknown"),
        "dock_state": dock_state,
        "charge_status": charge_name,
        "activity": "Returning to dock" if str(returning).lower() in ("1", "true") else ("Idle" if cleaning_name.lower() in ("complete", "none", "unknown") else cleaning_name),
        "cleaning_activity": "Returning to dock" if str(returning).lower() in ("1", "true") else ("Idle" if cleaning_name.lower() in ("complete", "none", "unknown") else cleaning_name),
        "current_room": current_room,
        "room": current_room,
        "cleaning_mode": mode_text,
        "cleaning_progress": clean_percent if clean_percent is not None else "Unknown",
        # Status clean_time is reported by Roborock in seconds.
        "cleaning_time_seconds": round(clean_time_seconds) if clean_time_seconds is not None else "Unknown",
        "cleaning_time_minutes": round(clean_time_seconds / 60, 1) if clean_time_seconds is not None else "Unknown",
        "cleaning_time": format_duration(clean_time_seconds),
        "area_cleaned_m2": round(number(session_area_m2), 1) if session_area_m2 is not None else "Unknown",
        # Clean-summary values are lifetime totals, separate from the current/last session.
        "total_cleaning_time_seconds": round(total_time_seconds) if total_time_seconds is not None else "Unknown",
        "total_cleaning_time_minutes": round(total_time_seconds / 60, 1) if total_time_seconds is not None else "Unknown",
        "total_cleaning_time": format_duration(total_time_seconds),
        "total_cleaned_area_m2": round(number(total_area_m2), 1) if total_area_m2 is not None else "Unknown",
        "total_cleaning_count": total_clean_count if total_clean_count is not None else "Unknown",
        "last_clean_run": last_clean_run,
        "error": enum_text(error_value, "Unknown"),
        "has_error": "No" if getattr(error_value, "value", error_value) in (0, "0", None) else "Yes",
        "dock_error": enum_text(dock_error),
        "dock_type": enum_text(dock_type),
        "map_present": "Yes" if map_present in (1, True, "1") else ("No" if map_present in (0, False, "0") else "Unknown"),
        "do_not_disturb": "Yes" if getattr(status, "dnd_enabled", None) in (1, True, "1") else ("No" if getattr(status, "dnd_enabled", None) in (0, False, "0") else "Unknown"),
        "last_refresh": datetime.now(TZ).isoformat(timespec="seconds"),
    }


def seconds_until_next_refresh(now: datetime | None = None) -> float:
    """Return seconds until the next wall-clock-aligned refresh slot."""
    cfg = config()
    now = now or datetime.now(TZ)
    segments = [
        (cfg["night_start"], cfg["night_end"], int(cfg["night_interval_seconds"])),
        ("04:00", cfg["peak_start"], int(cfg["default_interval_seconds"])),
        (cfg["peak_start"], cfg["peak_end"], int(cfg["peak_interval_seconds"])),
        (cfg["peak_end"], cfg["night_start"], int(cfg["default_interval_seconds"])),
    ]
    candidates: list[datetime] = []
    for day_offset in (0, 1, 2):
        day = now.date() + timedelta(days=day_offset)
        for start_text, end_text, interval in segments:
            start_clock, end_clock = time.fromisoformat(start_text), time.fromisoformat(end_text)
            start = datetime.combine(day, start_clock, tzinfo=TZ)
            end = datetime.combine(day, end_clock, tzinfo=TZ)
            if end_clock <= start_clock:
                end += timedelta(days=1)
            slot = start
            while slot < end:
                if slot > now:
                    candidates.append(slot)
                    break
                slot += timedelta(seconds=max(30, interval))
    return max(1.0, (min(candidates) - now).total_seconds()) if candidates else 3600.0


def operation_budget_allows() -> bool:
    cfg = config()
    used = int(usage().get("tracked_operations", 0))
    limit = max(1, int(cfg["daily_operation_limit"]))
    return used < limit * int(cfg.get("stop_percent", 90)) / 100


async def refresh_status(manual: bool = False) -> dict[str, Any]:
    async with state["refresh_lock"]:
        if state["status"] is None:
            await connect_device()
        if not manual and not operation_budget_allows():
            log.warning("Polling paused: tracked-operation safety threshold reached")
            return state["data"]
        await state["status"].refresh()

        # During cleaning, map content exposes the active room as vacuum_room.
        # Resolve it against a freshly refreshed mapping for the current map.
        current_room = "Unknown"
        robot_state = getattr(state["status"], "state", None)
        state_code = getattr(robot_state, "value", robot_state)
        if state_code in (5, 18, "5", "18"):
            properties = state["device"].v1_properties
            map_content = getattr(properties, "map_content", None)
            maps = getattr(properties, "maps", None)
            home = getattr(properties, "home", None)
            try:
                if map_content is not None:
                    await map_content.refresh()
                map_data = getattr(map_content, "map_data", None) if map_content is not None else None
                vacuum_room = getattr(map_data, "vacuum_room", None)
                if vacuum_room is not None and maps is not None and home is not None:
                    # Match the diagnostic endpoint's proven safe approach:
                    # refresh only the current map, never home.discover_home().
                    await maps.refresh()
                    current_map_info = getattr(maps, "current_map_info", None)
                    if current_map_info is not None:
                        refreshed_map_info = await home._refresh_map_info(current_map_info)
                        rooms = getattr(refreshed_map_info, "rooms", None) or []
                        for room in rooms:
                            segment_id = getattr(room, "segment_id", getattr(room, "id", None))
                            if str(segment_id) == str(vacuum_room):
                                current_room = str(getattr(room, "name", "Unknown"))
                                break
            except Exception as exc:
                log.warning("Could not resolve current cleaning room: %s", exc)

        # Lifetime totals are provided by the separate clean-summary trait.
        # Refresh it independently so the totals do not get confused with the
        # current/last cleaning session values in Status.
        clean_summary = getattr(state["device"].v1_properties, "clean_summary", None)
        if clean_summary is not None:
            try:
                await clean_summary.refresh()
            except Exception:
                log.exception("Could not refresh Roborock cleaning summary; retaining unavailable totals")
        data = current_status_data(state["status"], state["device"], current_room)
        state["data"] = data
        state["last_refresh"] = datetime.now(TZ).isoformat(timespec="seconds")
        counts = usage()
        counts["tracked_operations"] = int(counts.get("tracked_operations", 0)) + 1
        write_json(USAGE_FILE, counts)
        return data


def status_response() -> dict[str, Any]:
    cfg = config()
    counts = usage()
    used = int(counts.get("tracked_operations", 0))
    limit = max(1, int(cfg["daily_operation_limit"]))
    data = dict(state["data"])
    data.update({
        "last_refresh": state["last_refresh"] or data.get("last_refresh", "Unknown"),
        "night_start": cfg["night_start"],
        "night_end": cfg["night_end"],
        "night_interval_seconds": cfg["night_interval_seconds"],
        "peak_start": cfg["peak_start"],
        "peak_end": cfg["peak_end"],
        "peak_interval_seconds": cfg["peak_interval_seconds"],
        "default_interval_seconds": cfg["default_interval_seconds"],
        "daily_operation_limit": limit,
        "tracked_operations_today": used,
        "api_usage_percent": round(used * 100 / limit, 1),
        "operations_remaining": max(0, limit - used),
        "next_refresh": "Scheduled",
        "service_error": state["last_error"],
    })
    return {"data": data}


async def scheduler() -> None:
    # Refresh immediately on service start, then follow the wall-clock schedule.
    while True:
        try:
            if operation_budget_allows():
                await refresh_status()
            else:
                log.warning("Polling paused: tracked-operation safety threshold reached")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            state["last_error"] = str(exc)
            state["data"] = {**state["data"], "available": False, "error": str(exc)}
            log.exception("Scheduled status refresh failed")

        cfg = config()
        used = int(usage().get("tracked_operations", 0))
        limit = max(1, int(cfg["daily_operation_limit"]))
        delay = seconds_until_next_refresh()
        if used >= limit * int(cfg.get("slowdown_percent", 80)) / 100:
            delay = max(delay, int(cfg["default_interval_seconds"]) * 2)
        await asyncio.sleep(delay)


@asynccontextmanager
async def lifespan(app: FastAPI):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    usage()
    state["scheduler_task"] = asyncio.create_task(scheduler())
    yield
    task = state.get("scheduler_task")
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    if state["manager"] is not None:
        try:
            await state["manager"].close()
        except Exception:
            log.exception("Error closing Roborock manager")


app = FastAPI(title="Roborock Service", version="1.0.5", lifespan=lifespan)


class ServiceConfig(BaseModel):
    night_start: str = "03:00"
    night_end: str = "04:00"
    night_interval_seconds: int = Field(default=900, ge=30, le=86400)
    peak_start: str = "07:30"
    peak_end: str = "10:30"
    peak_interval_seconds: int = Field(default=600, ge=30, le=86400)
    default_interval_seconds: int = Field(default=3600, ge=30, le=86400)
    daily_operation_limit: int = Field(default=1000, ge=1)
    slowdown_percent: int = Field(default=80, ge=50, le=99)
    stop_percent: int = Field(default=90, ge=60, le=100)


@app.get("/health")
async def health():
    return {"ok": True, "connected": state["status"] is not None, "last_error": state["last_error"]}


@app.get("/status")
async def get_status():
    return status_response()


@app.get("/diagnostics/room")
async def get_room_diagnostic():
    """Read-only diagnostic for identifying the room currently being cleaned."""
    if state["status"] is None or state["device"] is None:
        raise HTTPException(status_code=503, detail="Roborock device is not connected")

    properties = state["device"].v1_properties
    home = getattr(properties, "home", None)
    maps = getattr(properties, "maps", None)
    current_map = getattr(maps, "current_map", None) if maps is not None else None
    room_maps = []
    room_refresh_error = None
    if home is not None and maps is not None:
        try:
            # Refresh only the current map's room mapping. Do not call
            # home.refresh()/discover_home() here: during segment_cleaning
            # the library's discovery guard does not recognise state 18
            # as generic cleaning and could attempt to switch maps.
            await maps.refresh()
            current_map = getattr(maps, "current_map", current_map)
            current_map_info = getattr(maps, "current_map_info", None)
            if current_map_info is not None:
                refreshed_map_info = await home._refresh_map_info(current_map_info)
                room_maps.append({
                    "map_flag": current_map,
                    "map_name": getattr(refreshed_map_info, "name", None),
                    "rooms": [
                        {
                            "segment_id": getattr(room, "segment_id", None),
                            "name": getattr(room, "name", None),
                        }
                        for room in (getattr(refreshed_map_info, "rooms", None) or [])
                    ],
                })
            else:
                room_refresh_error = "No current map information returned by maps.refresh()"
        except Exception as exc:
            room_refresh_error = f"{type(exc).__name__}: {exc}"
            log.warning("Current-map room refresh failed: %s", room_refresh_error)

    map_content = getattr(properties, "map_content", None)
    map_content_error = None
    try:
        if map_content is not None:
            await map_content.refresh()
    except Exception as exc:
        map_content_error = f"{type(exc).__name__}: {exc}"
        log.warning("Current map content refresh failed: %s", map_content_error)
    map_data = getattr(map_content, "map_data", None) if map_content is not None else None
    vacuum_room = getattr(map_data, "vacuum_room", None) if map_data is not None else None

    segment_status = None
    command_error = None
    try:
        segment_status = await properties.command.send(RoborockCommand.GET_SEGMENT_STATUS)
    except Exception as exc:
        command_error = f"{type(exc).__name__}: {exc}"
        log.warning("GET_SEGMENT_STATUS diagnostic request failed: %s", command_error)

    # Inspect public status fields and relevant device traits without calling
    # additional Roborock commands or invoking trait refresh methods.
    status_object = diagnostic_value(state["status"])
    trait_diagnostics: dict[str, Any] = {}
    keywords = ("segment", "room", "map", "status", "clean", "current")

    for trait_name in dir(properties):
        if trait_name.startswith("_") or not any(word in trait_name.lower() for word in keywords):
            continue
        try:
            trait = getattr(properties, trait_name)
        except Exception as exc:
            trait_diagnostics[trait_name] = {"read_error": f"{type(exc).__name__}: {exc}"}
            continue
        if trait is None or callable(trait) or isinstance(trait, (str, int, float, bool, list, tuple, dict)):
            continue

        fields: dict[str, Any] = {}
        try:
            names = set(vars(trait).keys())
        except TypeError:
            names = set()
        names.update(
            name for name in dir(trait)
            if not name.startswith("_") and any(word in name.lower() for word in keywords)
        )
        for field_name in sorted(names):
            if field_name.startswith("_"):
                continue
            try:
                field_value = getattr(trait, field_name)
                if not callable(field_value):
                    fields[field_name] = diagnostic_value(field_value)
            except Exception as exc:
                fields[field_name] = {"read_error": f"{type(exc).__name__}: {exc}"}
        trait_diagnostics[trait_name] = {
            "type": type(trait).__name__,
            "fields": fields,
        }

    return {
        "diagnostic_time": datetime.now(TZ).isoformat(timespec="seconds"),
        "device": str(getattr(state["device"], "name", "Roborock")),
        "robot_state": enum_text(getattr(state["status"], "state", None)),
        "current_map_flag": current_map,
        "room_maps": diagnostic_value(room_maps),
        "room_refresh_error": room_refresh_error,
        "get_segment_status": diagnostic_value(segment_status),
        "get_segment_status_error": command_error,
        "map_content_error": map_content_error,
        "map_vacuum_room": diagnostic_value(vacuum_room),
        "status_fields": status_object,
        "trait_diagnostics": trait_diagnostics,
    }


@app.get("/config")
async def get_config():
    return config()


@app.put("/config")
async def put_config(payload: ServiceConfig):
    values = payload.model_dump()
    try:
        for key in ("night_start", "night_end", "peak_start", "peak_end"):
            time.fromisoformat(values[key])
        if time.fromisoformat(values["night_start"]) >= time.fromisoformat(values["night_end"]):
            raise ValueError("Night window must not cross midnight")
        if time.fromisoformat(values["peak_start"]) >= time.fromisoformat(values["peak_end"]):
            raise ValueError("Peak window must not cross midnight")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Schedule times must use HH:MM and special windows must end after they start") from exc
    write_json(CONFIG_FILE, values)
    return values


@app.post("/refresh")
async def post_refresh():
    try:
        data = await refresh_status(manual=True)
        return {"ok": True, "data": data}
    except Exception as exc:
        state["last_error"] = str(exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return HTMLResponse("""
<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Roborock Service</title><style>
body{font:16px system-ui;max-width:760px;margin:35px auto;padding:0 18px;background:#f5f6f8;color:#20242a}
main{background:white;padding:24px;border-radius:14px;box-shadow:0 2px 12px #0001}
button{background:#1769aa;color:white;border:0;padding:12px 18px;border-radius:8px;font-size:16px;cursor:pointer}
button:disabled{opacity:.65;cursor:wait}
#refresh-feedback{margin:12px 0;padding:10px 12px;border-radius:8px;background:#eef2f6;color:#394554;min-height:22px}
#refresh-feedback.success{background:#e8f5ec;color:#176534}
#refresh-feedback.error{background:#fdecec;color:#a12626}
#refresh-feedback.busy{background:#e8f1fb;color:#17558b}
pre{white-space:pre-wrap;background:#f1f3f5;padding:14px;border-radius:8px}
</style></head><body><main><h1>Roborock Service</h1>
<p>Separate service for FiestaBoard. Roborock credentials remain on this NAS.</p>
<button id="refresh-button" onclick="refreshNow()">Refresh Now</button>
<div id="refresh-feedback" role="status" aria-live="polite">Ready. Status refreshes automatically every 15 seconds.</div>
<h2>Current status</h2><pre id="status">Loading…</pre>
<h2>Polling configuration</h2><pre id="config">Loading…</pre>
<script>
async function load(){try{let s=await fetch('/status');if(!s.ok)throw new Error('Status request failed ('+s.status+')');s=await s.json();document.getElementById('status').textContent=JSON.stringify(s.data,null,2);
let c=await fetch('/config');if(!c.ok)throw new Error('Configuration request failed ('+c.status+')');c=await c.json();document.getElementById('config').textContent=JSON.stringify(c,null,2)}catch(e){document.getElementById('status').textContent=String(e)}}
async function refreshNow(){
const button=document.getElementById('refresh-button');
const feedback=document.getElementById('refresh-feedback');
button.disabled=true;button.textContent='Refreshing…';
feedback.className='busy';feedback.textContent='Contacting your Roborock and requesting a fresh status…';
try{
const r=await fetch('/refresh',{method:'POST'});
const j=await r.json();
if(!r.ok)throw new Error(j.detail||'Refresh failed (HTTP '+r.status+')');
await load();
const refreshed=(j.data&&j.data.last_refresh)?new Date(j.data.last_refresh).toLocaleTimeString():'just now';
feedback.className='success';feedback.textContent='✓ Refresh successful — status updated at '+refreshed+'.';
}catch(e){
feedback.className='error';feedback.textContent='✕ Refresh failed — '+(e.message||String(e));
}finally{
button.disabled=false;button.textContent='Refresh Now';
}
}
load();setInterval(load,15000);
</script></main></body></html>""")


