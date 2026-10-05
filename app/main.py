"""Live Poll: one question, one button per option, one table entity per vote."""

import hashlib
import logging
import os
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

import segno
from azure.core.exceptions import AzureError
from azure.data.tables import TableClient, TableServiceClient
from azure.identity import ManagedIdentityCredential
from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

HERE = Path(__file__).parent
logger = logging.getLogger("livepoll")
COOKIE = "voted"
# Reads retry with backoff (0 s, 1 s, 2 s), 403 included: a new role assignment can take minutes to propagate.
RETRY = dict(retry_total=3, retry_backoff_factor=0.5, retry_on_status_codes=[403])


@dataclass(frozen=True)
class Settings:
    question: str
    options_raw: str
    color: str
    environment: str
    auth_mode: str
    table_name: str
    connection_string: str
    account_name: str
    client_id: str
    revision: str

    @property
    def auth_label(self) -> str:
        return "managed identity" if self.auth_mode == "identity" else self.auth_mode

    @property
    def options(self) -> list[str]:
        return [o.strip() for o in self.options_raw.split("|") if o.strip()]

    @property
    def poll_id(self) -> str:
        # A new question or option list is a new poll; old votes keep their own poll_id.
        # SPEC §4.3 fixes this formula (no separator), so the same question always maps to
        # the same poll. Collisions such as "A?x"+"|y" vs "A?"+"x|y" are accepted.
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
        account_name=os.environ.get("STORAGE_ACCOUNT_NAME", ""),
        client_id=os.environ.get("AZURE_CLIENT_ID", ""),
        # Container Apps sets this per revision; `or` also turns an empty value into "local".
        revision=os.environ.get("CONTAINER_APP_REVISION") or "local",
    )


@lru_cache
def get_table(settings: Settings = Depends(get_settings)) -> TableClient:
    # The app never creates the table: Terraform (or compose's table-init) owns it.
    if settings.auth_mode == "key":
        service = TableServiceClient.from_connection_string(settings.connection_string, **RETRY)
    elif settings.auth_mode == "identity":
        endpoint = f"https://{settings.account_name}.table.core.windows.net"
        credential = ManagedIdentityCredential(client_id=settings.client_id)
        service = TableServiceClient(endpoint, credential=credential, **RETRY)
    else:
        raise ValueError(f"AUTH_MODE must be key or identity, got {settings.auth_mode!r}")
    return service.get_table_client(settings.table_name)


def store_unreachable() -> JSONResponse:
    logger.exception("vote store unreachable")
    return JSONResponse({"error": "vote store unreachable"}, status_code=503)


def qr_svg(url: str) -> str:
    # Inline SVG with no fixed size so CSS sizes it. border=4 is the standard quiet zone.
    # No title/desc: the URL comes from the untrusted Host header and must not land in markup.
    return segno.make_qr(url, error="m").svg_inline(scale=10, border=4, dark="#000", light="#fff", omitsize=True)


app = FastAPI(title="Live Poll")
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")


def page_context(settings: Settings) -> dict:
    return {k: getattr(settings, k) for k in ("question", "options", "color", "environment")}


def render_vote_page(request: Request, settings: Settings, store_down: bool = False, status_code: int = 200):
    return templates.TemplateResponse(
        request,
        "vote.html",
        {
            **page_context(settings),
            "voted": request.cookies.get(COOKIE) == settings.poll_id,
            "store_down": store_down,
        },
        status_code=status_code,
    )


@app.get("/", response_class=HTMLResponse)
def vote_page(request: Request, settings: Settings = Depends(get_settings)):
    # Never touches storage, so the page renders even when the vote store is down.
    return render_vote_page(request, settings)


@app.get("/results", response_class=HTMLResponse)
def results_page(request: Request, settings: Settings = Depends(get_settings)):
    # Never touches storage either: results.js fetches the counts from /api/results.
    # The QR points at the host the projector used, so the app never needs its own FQDN.
    vote_url = str(request.url_for("vote_page"))
    return templates.TemplateResponse(
        request,
        "results.html",
        {
            **page_context(settings),
            "auth_label": settings.auth_label,
            "revision": settings.revision,
            "poll_id": settings.poll_id,
            "vote_url": vote_url,
            "qr": qr_svg(vote_url),
        },
    )


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.post("/api/vote")
def vote(
    request: Request,
    option: str = Form(),
    settings: Settings = Depends(get_settings),
    table: TableClient = Depends(get_table),
):
    poll_id = settings.poll_id
    if request.cookies.get(COOKIE) == poll_id:
        return JSONResponse({"error": "already voted"}, status_code=409)
    if option not in settings.options:
        return JSONResponse({"error": "unknown option"}, status_code=400)
    try:
        table.create_entity({"PartitionKey": poll_id, "RowKey": str(uuid4()), "option": option})
    except AzureError:
        if "text/html" in request.headers.get("accept", ""):
            # A phone's form post gets the page back with a banner; API clients keep the JSON.
            logger.exception("vote store unreachable")
            return render_vote_page(request, settings, store_down=True, status_code=503)
        return store_unreachable()
    response = RedirectResponse("/", status_code=303)
    # Soft guard against double voting, not real security. No Secure flag: local runs are plain HTTP.
    response.set_cookie(COOKIE, poll_id, max_age=86400, httponly=True, samesite="lax", path="/")
    return response


@app.get("/api/results")
def results(settings: Settings = Depends(get_settings), table: TableClient = Depends(get_table)):
    try:
        rows = table.query_entities(
            "PartitionKey eq @pk", parameters={"pk": settings.poll_id}, select=["option"]
        )
        counts = Counter(row["option"] for row in rows)
    except AzureError:
        return store_unreachable()
    return {
        "poll_id": settings.poll_id,
        "question": settings.question,
        "environment": settings.environment,
        "options": [{"option": o, "count": counts[o]} for o in settings.options],
        "total": sum(counts[o] for o in settings.options),
        # Lets an open /results tab notice a new revision and reload its footer.
        "revision": settings.revision,
    }
