"""Basic tests for the Robot Vacuum (Roborock) plugin."""

import json
from unittest.mock import MagicMock, patch

import pytest

from __init__ import RobotVacuumPlugin


@pytest.fixture
def manifest():
    return {
        "id": "robot_vacuum",
        "name": "Robot Vacuum (Roborock)",
        "version": "1.1.0",
    }


@pytest.fixture
def plugin(manifest):
    return RobotVacuumPlugin(manifest)


def test_plugin_id(plugin):
    assert plugin.plugin_id == "robot_vacuum"


def test_validate_config_missing_email(plugin):
    errors = plugin.validate_config({"user_data_json": "{}"})
    assert any("email" in e.lower() for e in errors)


def test_validate_config_missing_userdata(plugin):
    errors = plugin.validate_config({"email": "test@example.com"})
    assert any("userdata" in e.lower() for e in errors)


def test_validate_config_invalid_json(plugin):
    errors = plugin.validate_config(
        {"email": "test@example.com", "user_data_json": "not-json"}
    )
    assert any("json" in e.lower() for e in errors)


def test_validate_config_ok(plugin):
    errors = plugin.validate_config(
        {
            "email": "test@example.com",
            "user_data_json": json.dumps({"rriot": {"u": "x", "s": "y"}}),
        }
    )
    assert errors == []


def test_on_config_change_clears_cache(plugin):
    plugin._cache = {"dummy": True}
    plugin._user_params = object()
    plugin._device_manager = object()
    plugin.on_config_change({}, {"email": "new@example.com"})
    assert plugin._cache is None
    assert plugin._user_params is None
    assert plugin._device_manager is None
