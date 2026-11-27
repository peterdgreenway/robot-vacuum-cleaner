"""Basic unit tests for the FiestaBoard service-backed plugin."""
from unittest.mock import patch

from __init__ import RobotVacuumPlugin, _display_activity, _fit


def plugin():
    return RobotVacuumPlugin({"id": "robot_vacuum_cleaner", "version": "2.1.0"})


def test_plugin_id_matches_manifest():
    assert plugin().plugin_id == "robot_vacuum_cleaner"


def test_fit():
    assert _fit("abcdefghijklmnopqrstuvwxyz") == "ABCDEFGHIJKLMNO"
    assert _fit(None) == ""



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


def test_validate_config():
    p = plugin()
    assert p.validate_config({"service_url": "http://nas:8088", "night_interval_seconds": 900, "peak_interval_seconds": 600, "default_interval_seconds": 3600}) == []
    assert p.validate_config({"service_url": "nas:8088"})[0].startswith("Service URL")


def test_fetch_status_and_schedule():
    p = plugin()
    p.config = {"service_url": "http://nas:8088", "night_start": "03:00", "night_end": "04:00", "night_interval_seconds": 900, "peak_start": "07:30", "peak_end": "10:30", "peak_interval_seconds": 600, "default_interval_seconds": 3600, "daily_operation_limit": 1000}

    def fake(path, method="GET", payload=None):
        if path == "/status":
            return {"data": {"name": "Saros 20", "battery_level": 42, "is_charging": False, "is_docked": True, "activity": "segment_clean_not_complete", "robot_state": "segment_cleaning", "cleaning_mode": "vacuum", "current_room": "Kitchen"}}
        return {}

    with patch.object(p, "_request", side_effect=fake):
        result = p.fetch_data()
    assert result.available
    assert result.data["battery"] == "42%"
    assert result.data["line2"] == "VACUUMING"\n    assert result.data["line3"] == "KITCHEN"


def test_time_of_day_schedule_is_sent_to_service():
    p = plugin()
    p.config = {"service_url": "http://nas:8088", "night_start": "03:00", "night_end": "04:00", "night_interval_seconds": 900, "peak_start": "07:30", "peak_end": "10:30", "peak_interval_seconds": 600, "default_interval_seconds": 3600, "daily_operation_limit": 1000}
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
