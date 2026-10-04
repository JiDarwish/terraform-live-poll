import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main  # noqa: E402


def make_settings(**overrides):
    values = dict(
        question="How confident are you with Terraform?",
        options_raw="What's Terraform?|Heard of it|Used it|I could teach this",
        color="#2f7d5b",
        environment="dev",
        auth_mode="key",
        table_name="votes",
        connection_string="UseDevelopmentStorage=true",
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
def client(settings_override):
    with TestClient(main.app) as c:
        yield c
