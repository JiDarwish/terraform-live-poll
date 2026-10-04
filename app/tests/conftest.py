import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main  # noqa: E402


class FakeTable:
    """In-memory stand-in for azure.data.tables.TableClient."""

    def __init__(self, error=None):
        self.entities = []
        self.error = error

    def create_entity(self, entity):
        if self.error:
            raise self.error
        self.entities.append(dict(entity))

    def query_entities(self, query_filter, parameters=None, select=None):
        if self.error:
            raise self.error
        assert query_filter == "PartitionKey eq @pk"
        rows = [e for e in self.entities if e["PartitionKey"] == parameters["pk"]]
        return [{k: e[k] for k in select} if select else e for e in rows]


def make_settings(**overrides):
    values = dict(
        question="How confident are you with Terraform?",
        options_raw="What's Terraform?|Heard of it|Used it|I could teach this",
        color="#2f7d5b",
        environment="dev",
        auth_mode="key",
        table_name="votes",
        connection_string="UseDevelopmentStorage=true",
        revision="local",
    )
    values.update(overrides)
    return main.Settings(**values)


@pytest.fixture
def settings_override():
    """Mutable holder so a test can switch the poll mid-test."""
    holder = {"settings": make_settings()}
    main.app.dependency_overrides[main.get_settings] = lambda: holder["settings"]
    yield holder
    main.app.dependency_overrides.clear()


@pytest.fixture
def table():
    fake = FakeTable()
    main.app.dependency_overrides[main.get_table] = lambda: fake
    return fake


@pytest.fixture
def client(settings_override, table):
    with TestClient(main.app) as c:
        yield c
