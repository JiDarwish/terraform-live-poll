"""Live Poll: one question, one button per option, one table entity per vote."""

import hashlib
import os
from dataclasses import dataclass
from functools import lru_cache

from fastapi import FastAPI


@dataclass(frozen=True)
class Settings:
    question: str
    options_raw: str
    color: str
    environment: str
    auth_mode: str
    table_name: str
    connection_string: str

    @property
    def options(self) -> list[str]:
        return [o.strip() for o in self.options_raw.split("|") if o.strip()]

    @property
    def poll_id(self) -> str:
        # A new question or option list is a new poll; old votes keep their own poll_id.
        return hashlib.sha256((self.question + self.options_raw).encode()).hexdigest()[:8]


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} must be set")
    return value


@lru_cache
def get_settings() -> Settings:
    return Settings(
        question=_required("POLL_QUESTION"),
        options_raw=_required("POLL_OPTIONS"),
        color=os.environ.get("POLL_COLOR", "#2f7d5b"),
        environment=os.environ.get("ENVIRONMENT", "dev"),
        auth_mode=os.environ.get("AUTH_MODE", "key"),
        table_name=os.environ.get("TABLE_NAME", "votes"),
        connection_string=os.environ.get("STORAGE_CONNECTION_STRING", ""),
    )


app = FastAPI(title="Live Poll")


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
