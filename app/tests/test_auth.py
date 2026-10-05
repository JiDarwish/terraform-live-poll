import json

import pytest
import requests
from azure.core.exceptions import HttpResponseError
from azure.core.pipeline.transport import HttpTransport, RequestsTransportResponse
from azure.data.tables import TableServiceClient

import main
from conftest import make_settings

AZURITE = (
    "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;"
    "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;"
    "TableEndpoint=http://127.0.0.1:10002/devstoreaccount1;"
)


@pytest.fixture(autouse=True)
def fresh_cache():
    main.get_table.cache_clear()
    main.get_settings.cache_clear()
    yield
    main.get_table.cache_clear()
    main.get_settings.cache_clear()


class FakeService:
    def __init__(self, calls):
        self.calls = calls

    def get_table_client(self, name):
        self.calls["table"] = name
        return "table-client"


def test_key_mode_uses_connection_string(monkeypatch):
    calls = {}

    def from_connection_string(conn_str, **kwargs):
        calls.update(conn=conn_str, kwargs=kwargs)
        return FakeService(calls)

    monkeypatch.setattr(main.TableServiceClient, "from_connection_string", from_connection_string)
    client_ = main.get_table(make_settings(connection_string="cs", table_name="t1"))
    assert client_ == "table-client"
    assert calls == {"conn": "cs", "kwargs": main.RETRY, "table": "t1"}


def test_identity_mode_uses_managed_identity(monkeypatch):
    calls = {}

    class FakeCredential:
        def __init__(self, client_id):
            self.client_id = client_id

    class FakeServiceClient(FakeService):
        def __init__(self, endpoint, credential, **kwargs):
            super().__init__(calls)
            calls.update(endpoint=endpoint, credential=credential, kwargs=kwargs)

        @classmethod
        def from_connection_string(cls, *args, **kwargs):
            calls["from_connection_string"] = True

    monkeypatch.setattr(main, "ManagedIdentityCredential", FakeCredential)
    monkeypatch.setattr(main, "TableServiceClient", FakeServiceClient)
    settings = make_settings(auth_mode="identity", account_name="stlivepolldevxx01", client_id="cid", table_name="t1")
    client_ = main.get_table(settings)
    assert client_ == "table-client"
    assert calls["endpoint"] == "https://stlivepolldevxx01.table.core.windows.net"
    assert isinstance(calls["credential"], FakeCredential)
    assert calls["credential"].client_id == "cid"
    assert calls["kwargs"] == main.RETRY
    assert calls["table"] == "t1"
    assert "from_connection_string" not in calls


def test_unknown_auth_mode_raises():
    with pytest.raises(ValueError, match="AUTH_MODE"):
        main.get_table(make_settings(auth_mode="sas"))


def test_identity_settings_from_env(monkeypatch):
    monkeypatch.setenv("POLL_QUESTION", "Q?")
    monkeypatch.setenv("POLL_OPTIONS", "a|b")
    monkeypatch.setenv("AUTH_MODE", "identity")
    monkeypatch.setenv("STORAGE_ACCOUNT_NAME", "stlivepolldevxx01")
    monkeypatch.setenv("AZURE_CLIENT_ID", "cid")
    s = main.get_settings()
    assert (s.auth_mode, s.account_name, s.client_id) == ("identity", "stlivepolldevxx01", "cid")


class FakeTransport(HttpTransport):
    """Answers every request with 403 and records the method."""

    def __init__(self):
        self.methods = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def open(self):
        pass

    def close(self):
        pass

    def send(self, request, **kwargs):
        self.methods.append(request.method)
        raw = requests.Response()
        raw.status_code = 403
        raw.headers["Content-Type"] = "application/json"
        raw._content = json.dumps(
            {"odata.error": {"code": "AuthorizationPermissionMismatch", "message": {"value": "no role yet"}}}
        ).encode()
        return RequestsTransportResponse(request, raw)


def test_reads_retry_403_with_backoff_writes_do_not(monkeypatch):
    slept = []
    monkeypatch.setattr("time.sleep", slept.append)
    transport = FakeTransport()
    service = TableServiceClient.from_connection_string(AZURITE, transport=transport, **main.RETRY)
    table = service.get_table_client("votes")

    with pytest.raises(HttpResponseError):
        list(table.query_entities("PartitionKey eq @pk", parameters={"pk": "x"}))
    assert transport.methods == ["GET"] * 4
    assert slept == [1.0, 2.0]

    transport.methods.clear()
    with pytest.raises(HttpResponseError):
        table.create_entity({"PartitionKey": "x", "RowKey": "1"})
    assert transport.methods == ["POST"]
