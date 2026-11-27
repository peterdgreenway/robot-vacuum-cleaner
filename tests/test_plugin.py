"""Basic unit tests for the FiestaBoard service-backed plugin."""
from unittest.mock import patch

from __init__ import RobotVacuumPlugin, _fit


def plugin():
    return RobotVacuumPlugin({"id": "robot_vacuum_cleaner", "version": "2.0.0"})


def test_plugin_id_matches_manifest():
    assert plugin().plugin_id == "robot_vacuum_cleaner"


def test_fit():
    assert _fit("abcdefghijklmnopqrstuvwxyz") == "ABCDEFGHIJKLMNO"
    assert _fit(None) == ""


def test_validate_config():
    p = plugin()
    assert p.validate_config({"service_url": "http://nas:8088", "polling_interval_seconds": 60}) == []
    assert p.validate_config({"service_url": "nas:8088"})[0].startswith("Service URL")


def test_fetch_status_and_schedule():
    p = plugin()
    p.config = {"service_url": "http://nas:8088", "polling_start": "07:15", "polling_end": "21:00", "polling_interval_seconds": 60, "daily_operation_limit": 1000}

    def fake(path, method="GET", payload=None):
        if path == "/status":
            return {"data": {"name": "Saros 20", "battery_level": 42, "is_charging": False, "is_docked": True, "activity": "Vacuuming", "current_room": "Kitchen"}}
        return {}

    with patch.object(p, "_request", side_effect=fake):
        result = p.fetch_data()
    assert result.available
    assert result.data["battery"] == "42%"
    assert result.data["line3"] == "KITCHEN"
