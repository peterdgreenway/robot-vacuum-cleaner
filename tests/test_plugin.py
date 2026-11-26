"""Tests – every returned string must be ≤ 15 characters."""

import json
import pytest
from __init__ import RobotVacuumPlugin, _fit


@pytest.fixture
def plugin():
    return RobotVacuumPlugin({"id": "robot_vacuum", "version": "1.2.0"})


def test_fit_truncates():
    assert len(_fit("ABCDEFGHIJKLMNOPQRSTUVWXYZ")) == 15
    assert _fit("clean") == "CLEAN"
    assert _fit(None) == ""


def test_validate_missing_email(plugin):
    errs = plugin.validate_config({"user_data_json": "{}"})
    assert any("email" in e.lower() for e in errs)


def test_validate_bad_json(plugin):
    errs = plugin.validate_config(
        {"email": "a@b.c", "user_data_json": "not-json"}
    )
    assert any("json" in e.lower() for e in errs)


def test_validate_ok(plugin):
    errs = plugin.validate_config(
        {"email": "a@b.c", "user_data_json": "{}"}
    )
    assert errs == []
