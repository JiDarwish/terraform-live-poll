import hashlib
import os
import uuid

import pytest
from azure.core.exceptions import AzureError
from fastapi.testclient import TestClient

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


# --- phone vote page ------------------------------------------------------

def test_page_renders(client, settings_override):
    s = settings_override["settings"]
    r = client.get("/")
    assert r.status_code == 200
    html = r.text
    assert s.question in html
    assert html.count("<button") == len(s.options)
    assert "DEV" in html
    assert "#2f7d5b" in html
    assert 'name="viewport"' in html
    assert "<script" not in html


def test_page_shows_thanks_after_vote(client):
    client.post("/api/vote", data={"option": "Used it"}, follow_redirects=False)
    html = client.get("/").text
    assert "Thanks, look at the screen" in html
    assert 'href="/api/results"' in html
    assert "<button" not in html


def test_page_renders_prod_badge(client, settings_override):
    settings_override["settings"] = make_settings(environment="prod", color="#123456")
    html = client.get("/").text
    assert "PROD" in html
    assert "badge-prod" in html
    assert "#123456" in html


def test_static_css_served(client):
    r = client.get("/static/style.css")
    assert r.status_code == 200
    assert ".badge-dev" in r.text


def test_page_does_not_touch_storage(client):
    def broken_table():
        raise RuntimeError("storage must not be touched by /")

    main.app.dependency_overrides[main.get_table] = broken_table
    assert client.get("/").status_code == 200
    assert client.get("/healthz").status_code == 200


# --- optional: against a real Azurite -------------------------------------

@pytest.mark.skipif(
    not os.getenv("AZURITE_CONNECTION_STRING"),
    reason="set AZURITE_CONNECTION_STRING to run against a real Azurite",
)
def test_vote_against_azurite(settings_override):
    # The question is unique per run so earlier runs' votes don't count.
    settings = make_settings(
        question=f"Integration {uuid.uuid4()}?",
        connection_string=os.environ["AZURITE_CONNECTION_STRING"],
    )
    settings_override["settings"] = settings
    service = main.TableServiceClient.from_connection_string(settings.connection_string)
    service.create_table_if_not_exists(settings.table_name)
    main.get_table.cache_clear()
    with TestClient(main.app) as client:
        r = client.post("/api/vote", data={"option": "Used it"}, follow_redirects=False)
        assert r.status_code == 303
        body = client.get("/api/results").json()
    main.get_table.cache_clear()
    assert body["total"] == 1
    assert {"option": "Used it", "count": 1} in body["options"]
