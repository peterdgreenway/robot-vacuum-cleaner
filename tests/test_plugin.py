"""Basic unit tests for the FiestaBoard service-backed plugin."""
from unittest.mock import patch

from __init__ import RobotVacuumPlugin, _display_activity, _fit, _timestamp_parts


def plugin():
    return RobotVacuumPlugin({"id": "robot_vacuum_cleaner", "version": "2.2.0"})


def test_plugin_id_matches_manifest():
    assert plugin().plugin_id == "robot_vacuum_cleaner"


def test_fit():
    assert _fit("abcdefghijklmnopqrstuvwxyz") == "ABCDEFGHIJKLMNO"
    assert _fit(None) == ""


def test_timestamp_parts_use_london_format():
    parts = _timestamp_parts("2026-11-27T18:11:00+00:00")
    assert parts == {
        "date": "27-NOV-26",
        "time": "18:11",
        "datetime": "27-NOV-26 18:11",
    }
    assert _timestamp_parts(None)["datetime"] == "NOT AVAILABLE"


def test_display_activity_uses_friendly_labels():
    assert _display_activity({
        "robot_state": "segment_cleaning",
        "activity": "segment_clean_not_complete",
        "cleaning_mode": "vacuum",
    }) == "VACUUMING"
    assert _display_activity({
        "robot_state": "segment_cleaning",
        "activity": "segment_clean_not_complete",
        "cleaning_mode": "mop",
    }) == "MOPPING"
    assert _display_activity({"robot_state": "charging"}) == "CHARGING"
    assert _display_activity({"robot_state": "returning"}) == "RETURNING"
    assert _display_activity({"robot_state": "cruising"}) == "PATROLLING"


def test_validate_config():
    p = plugin()
    assert p.validate_config({
        "service_url": "http://nas:8088",
        "night_interval_seconds": 900,
        "peak_interval_seconds": 600,
        "default_interval_seconds": 3600,
    }) == []
    assert p.validate_config({"service_url": "nas:8088"})[0].startswith("Service URL")


def test_fetch_status_and_schedule():
    p = plugin()
    p.config = {
        "service_url": "http://nas:8088", "night_start": "03:00",
        "night_end": "04:00", "night_interval_seconds": 900,
        "peak_start": "07:30", "peak_end": "10:30",
        "peak_interval_seconds": 600, "default_interval_seconds": 3600,
        "daily_operation_limit": 1000,
    }

    def fake(path, method="GET", payload=None):
        if path == "/status":
            return {"data": {
                "name": "Saros 20", "battery_level": 42, "is_charging": False,
                "is_docked": True, "activity": "segment_clean_not_complete",
                "robot_state": "segment_cleaning", "cleaning_mode": "vacuum",
                "current_room": "Kitchen",
                "last_clean_run": "2026-11-27T18:11:00+00:00",
                "last_refresh": "2026-11-27T18:12:00+00:00",
                "total_cleaning_time": "4h 5m",
                "total_cleaning_time_seconds": 14700,
                "total_cleaned_area_m2": 1234.5,
            }}
        return {}

    with patch.object(p, "_request", side_effect=fake):
        result = p.fetch_data()
    assert result.available
    assert result.data["battery"] == "42%"
    assert result.data["line2"] == "VACUUMING"
    assert result.data["line3"] == "KITCHEN"
    assert result.data["last_run_date"] == "27-NOV-26"
    assert result.data["last_run_time"] == "18:11"
    assert result.data["last_run_datetime"] == "27-NOV-26 18:11"
    assert result.data["last_refresh_date"] == "27-NOV-26"
    assert result.data["last_refresh_time"] == "18:12"
    assert result.data["last_refresh_datetime"] == "27-NOV-26 18:12"
    assert result.data["total_cleaning_time"] == "4h 5m"
    assert result.data["total_cleaned_area_m2"] == 1234.5



def test_last_run_room_and_operation_survive_return_to_dock():
    p = plugin()
    p.config = {
        "service_url": "http://nas:8088", "night_start": "03:00",
        "night_end": "04:00", "night_interval_seconds": 900,
        "peak_start": "07:30", "peak_end": "10:30",
        "peak_interval_seconds": 600, "default_interval_seconds": 3600,
        "daily_operation_limit": 1000,
    }
    responses = [
        {"data": {
            "name": "Saros 20", "battery_level": 35, "is_docked": False,
            "robot_state": "segment_cleaning", "activity": "segment_clean_not_complete",
            "cleaning_mode": "vacuum", "current_room": "Living room",
        }},
        {"data": {
            "name": "Saros 20", "battery_level": 40, "is_docked": True,
            "robot_state": "charging", "activity": "charging",
            "cleaning_mode": "not available", "current_room": "NOT AVAILABLE",
        }},
    ]

    def fake(path, method="GET", payload=None):
        if path == "/status":
            return responses.pop(0)
        return {}

    with patch.object(p, "_request", side_effect=fake):
        first = p.fetch_data()
        assert first.data["last_run_room"] == "Living room"
        assert first.data["last_run_operation"] == "VACUUM"
        p._cache_ts = 0  # Force the next status fetch rather than using the cache.
        second = p.fetch_data()

    assert second.available
    assert second.data["last_run_room"] == "Living room"
    assert second.data["last_run_operation"] == "VACUUM"
    assert second.data["current_room"] == "NOT AVAILABLE"
    assert second.data["line2"] == "CHARGING"


def test_time_of_day_schedule_is_sent_to_service():
    p = plugin()
    p.config = {
        "service_url": "http://nas:8088", "night_start": "03:00",
        "night_end": "04:00", "night_interval_seconds": 900,
        "peak_start": "07:30", "peak_end": "10:30",
        "peak_interval_seconds": 600, "default_interval_seconds": 3600,
        "daily_operation_limit": 1000,
    }
    calls = []

    def fake(path, method="GET", payload=None):
        calls.append((path, method, payload))
        if path == "/status":
            return {"data": {"name": "Saros 20", "battery_level": 80}}
        return {}

    with patch.object(p, "_request", side_effect=fake):
        result = p.fetch_data()
    config_call = next(c for c in calls if c[0] == "/config")
    assert config_call[2]["night_interval_seconds"] == 900
    assert config_call[2]["peak_interval_seconds"] == 600
    assert config_call[2]["default_interval_seconds"] == 3600
    assert result.available
