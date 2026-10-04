import hashlib
import uuid

import pytest
from azure.core.exceptions import AzureError

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


# --- vote store -----------------------------------------------------------

def results(client):
    r = client.get("/api/results")
    assert r.status_code == 200
    return r.json()


def test_vote_then_results_counts_up(client, settings_override):
    s = settings_override["settings"]
    assert results(client)["total"] == 0
    r = client.post("/api/vote", data={"option": "Used it"}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/"
    body = results(client)
    assert body["poll_id"] == s.poll_id
    assert body["question"] == s.question
    assert body["environment"] == "dev"
    assert body["total"] == 1
    assert body["options"] == [
        {"option": o, "count": 1 if o == "Used it" else 0} for o in s.options
    ]


def test_entity_shape(client, table, settings_override):
    client.post("/api/vote", data={"option": "Heard of it"}, follow_redirects=False)
    (entity,) = table.entities
    assert entity["PartitionKey"] == settings_override["settings"].poll_id
    assert uuid.UUID(entity["RowKey"])
    assert entity["option"] == "Heard of it"


def test_vote_sets_cookie(client, settings_override):
    r = client.post("/api/vote", data={"option": "Used it"}, follow_redirects=False)
    cookie = r.headers["set-cookie"]
    assert f"voted={settings_override['settings'].poll_id}" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie or "samesite=lax" in cookie.lower()


def test_second_vote_same_poll_refused(client, table):
    client.post("/api/vote", data={"option": "Used it"}, follow_redirects=False)
    r = client.post("/api/vote", data={"option": "Heard of it"}, follow_redirects=False)
    assert r.status_code == 409
    assert r.json() == {"error": "already voted"}
    assert len(table.entities) == 1
    assert results(client)["total"] == 1


def test_new_poll_starts_at_zero_old_votes_kept(client, table, settings_override):
    old_id = settings_override["settings"].poll_id
    client.post("/api/vote", data={"option": "Used it"}, follow_redirects=False)
    settings_override["settings"] = make_settings(question="Other?")
    body = results(client)
    assert body["poll_id"] != old_id
    assert body["total"] == 0
    assert [e["PartitionKey"] for e in table.entities] == [old_id]
    # The phone still holds the old poll's cookie; it must not block the new poll.
    r = client.post("/api/vote", data={"option": "Used it"}, follow_redirects=False)
    assert r.status_code == 303
    assert results(client)["total"] == 1


def test_unknown_option_400(client, table):
    r = client.post("/api/vote", data={"option": "Nope"}, follow_redirects=False)
    assert r.status_code == 400
    assert table.entities == []


def test_store_error_returns_503(client, table):
    table.error = AzureError("boom")
    r = client.post("/api/vote", data={"option": "Used it"}, follow_redirects=False)
    assert r.status_code == 503
    assert r.json() == {"error": "vote store unreachable"}
    assert "voted" not in r.headers.get("set-cookie", "")
    r = client.get("/api/results")
    assert r.status_code == 503
    assert r.json() == {"error": "vote store unreachable"}


def test_key_mode_uses_connection_string(monkeypatch):
    calls = {}

    class FakeService:
        def get_table_client(self, name):
            calls["table"] = name
            return "table-client"

    def from_connection_string(conn_str):
        calls["conn"] = conn_str
        return FakeService()

    monkeypatch.setattr(main.TableServiceClient, "from_connection_string", from_connection_string)
    main.get_table.cache_clear()
    try:
        client_ = main.get_table(make_settings(connection_string="cs", table_name="t1"))
    finally:
        main.get_table.cache_clear()
    assert client_ == "table-client"
    assert calls == {"conn": "cs", "table": "t1"}


def test_non_key_auth_mode_raises():
    main.get_table.cache_clear()
    with pytest.raises(ValueError, match="#3"):
        main.get_table(make_settings(auth_mode="identity"))
