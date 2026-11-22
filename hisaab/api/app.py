"""FastAPI application. Run with: uvicorn hisaab.api.app:app --reload

Synchronous endpoints run on FastAPI's worker thread pool, so requests to the
same group really do run concurrently; the services handle that (FR-13).

Identity: at M2 the caller is identified by the X-User-Id header. Real
authentication is out of scope for the course; see risk R10.
"""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from hisaab.api.errors import install_error_handlers, request_id_var
from hisaab.api.routes import expenses, groups, ledger, reports, users
from hisaab.bootstrap import Container, build_sqlite


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.addFilter(_RequestIdFilter())
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s")
    )
    root = logging.getLogger("hisaab")
    root.handlers[:] = [handler]
    root.setLevel(level)


def create_app(container: Container | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if getattr(app.state, "container", None) is None:
            app.state.container = build_sqlite(os.environ.get("HISAAB_DB", "data/hisaab.db"))
        yield
        app.state.container.close()

    app = FastAPI(title="Hisaab", version="0.2.0", lifespan=lifespan)
    app.state.container = container

    @app.middleware("http")
    async def request_id(request: Request, call_next):  # type: ignore[no-untyped-def]
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        token = request_id_var.set(rid)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = rid
        return response

    install_error_handlers(app)
    for module in (users, groups, expenses, ledger, reports):
        app.include_router(module.router)
    return app


def _default_app() -> FastAPI:
    os.makedirs("data", exist_ok=True)
    configure_logging()
    return create_app()


app = _default_app()
