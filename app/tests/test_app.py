import hashlib

import pytest

import main
from conftest import make_settings


# --- settings and poll_id -------------------------------------------------

def test_poll_id_is_stable_8_hex():
    s = make_settings(question="Q?", options_raw="a|b")
    expected = hashlib.sha256("Q?a|b".encode()).hexdigest()[:8]
    assert s.poll_id == expected
    assert make_settings(question="Q?", options_raw="a|b").poll_id == expected


def test_poll_id_changes_with_question():
    assert make_settings(question="A?").poll_id != make_settings(question="B?").poll_id


def test_poll_id_changes_with_options():
    assert make_settings(options_raw="a|b").poll_id != make_settings(options_raw="a|c").poll_id


def test_options_split_and_trimmed():
    assert make_settings(options_raw=" a | b ||c ").options == ["a", "b", "c"]


def test_healthz_200(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_missing_question_fails_clearly(monkeypatch):
    monkeypatch.delenv("POLL_QUESTION", raising=False)
    monkeypatch.setenv("POLL_OPTIONS", "a|b")
    main.get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="POLL_QUESTION"):
        main.get_settings()
    main.get_settings.cache_clear()


def test_settings_defaults_from_env(monkeypatch):
    for var in ("ENVIRONMENT", "POLL_COLOR", "TABLE_NAME", "AUTH_MODE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("POLL_QUESTION", "Q?")
    monkeypatch.setenv("POLL_OPTIONS", "a|b")
    main.get_settings.cache_clear()
    s = main.get_settings()
    main.get_settings.cache_clear()
    assert (s.environment, s.color, s.table_name, s.auth_mode) == ("dev", "#2f7d5b", "votes", "key")
