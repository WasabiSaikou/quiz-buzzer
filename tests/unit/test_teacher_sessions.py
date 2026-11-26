"""TeacherSessions: passcode check and in-memory session tokens (002 research R1, FR-001–FR-003)."""

from __future__ import annotations

import re

import pytest

from quizbuzzer.api import auth
from quizbuzzer.api.auth import TeacherSessions, WrongPasscode


def test_wrong_passcode_raises():
    sessions = TeacherSessions("right-pass")
    with pytest.raises(WrongPasscode):
        sessions.create("wrong-pass")
    with pytest.raises(WrongPasscode):
        sessions.create("")


def test_right_passcode_returns_a_valid_token():
    sessions = TeacherSessions("right-pass")
    token = sessions.create("right-pass")
    assert len(token) >= 43
    assert re.fullmatch(r"[A-Za-z0-9_-]+", token)
    assert sessions.is_valid(token)


@pytest.mark.parametrize("token", ["", None, "not-a-token"])
def test_unknown_tokens_are_invalid(token):
    sessions = TeacherSessions("right-pass")
    sessions.create("right-pass")
    assert not sessions.is_valid(token)


def test_several_tabs_get_distinct_valid_tokens():
    sessions = TeacherSessions("right-pass")
    t1, t2 = sessions.create("right-pass"), sessions.create("right-pass")
    assert t1 != t2
    assert sessions.is_valid(t1) and sessions.is_valid(t2)


def test_restart_forgets_tokens():
    token = TeacherSessions("right-pass").create("right-pass")
    assert not TeacherSessions("right-pass").is_valid(token)


def test_comparison_is_constant_time(monkeypatch):
    calls = []
    real = auth.hmac.compare_digest

    def recording(a, b):
        calls.append((type(a), type(b)))
        return real(a, b)

    monkeypatch.setattr(auth.hmac, "compare_digest", recording)
    sessions = TeacherSessions("right-pass")
    sessions.create("right-pass")
    with pytest.raises(WrongPasscode):
        sessions.create("nope")
    assert calls == [(bytes, bytes), (bytes, bytes)]
