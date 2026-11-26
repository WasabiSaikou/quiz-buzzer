"""TEACHER_PASSCODE configuration (002 research R1, FR-004). Never reads the real .env."""

from __future__ import annotations

import pytest

from quizbuzzer.config import ConfigError, Settings, load_settings
from quizbuzzer.main import create_app


@pytest.mark.parametrize("value", [None, "", "   ", "\t\n"])
def test_blank_or_missing_passcode_refused(monkeypatch, value):
    monkeypatch.delenv("TEACHER_PASSCODE", raising=False)
    if value is not None:
        monkeypatch.setenv("TEACHER_PASSCODE", value)
    with pytest.raises(ConfigError) as info:
        load_settings(env_file=None)
    assert "TEACHER_PASSCODE" in str(info.value)


def test_passcode_is_loaded_and_stripped(monkeypatch):
    monkeypatch.setenv("TEACHER_PASSCODE", "  s3cret-value  ")
    settings = load_settings(env_file=None)
    assert settings.teacher_passcode == "s3cret-value"


def test_error_message_never_contains_a_value(monkeypatch):
    monkeypatch.setenv("TEACHER_PASSCODE", "   ")
    with pytest.raises(ConfigError) as info:
        load_settings(env_file=None)
    assert str(info.value) == "TEACHER_PASSCODE is not set in .env."


def test_create_app_refuses_blank_passcode(db_path, fake_adapter):
    settings = Settings(
        credentials_path=None, db_path=db_path, host="127.0.0.1", port=8000, teacher_passcode=""
    )
    with pytest.raises(ConfigError, match="TEACHER_PASSCODE"):
        create_app(adapter=fake_adapter, db_path=db_path, settings=settings)
