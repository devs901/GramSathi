"""Small HTTP toolkit on top of Starlette: JSON helpers, validation, auth + DB injection."""
from __future__ import annotations

import functools
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

from pydantic import BaseModel, ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from . import db as dbm
from .security import decode_token

M = TypeVar("M", bound=BaseModel)


class ApiError(Exception):
    def __init__(self, status: int, message: str, details: Any = None):
        self.status, self.message, self.details = status, message, details


def ok(data: Any = None, status: int = 200) -> JSONResponse:
    return JSONResponse(data if data is not None else {"ok": True}, status_code=status)


def error_response(status: int, message: str, details: Any = None) -> JSONResponse:
    body: dict[str, Any] = {"error": message}
    if details is not None:
        body["details"] = details
    return JSONResponse(body, status_code=status)


async def parse(request: Request, model: type[M]) -> M:
    try:
        payload = await request.json()
    except Exception:
        raise ApiError(400, "Request body must be valid JSON")
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        details = [{"field": ".".join(str(p) for p in e["loc"]), "message": e["msg"]} for e in exc.errors()]
        raise ApiError(422, "Validation failed", details)


@dataclass
class Ctx:
    db: sqlite3.Connection
    user: dict | None
    settings: Any
    request: Request

    @property
    def is_admin(self) -> bool:
        return bool(self.user and self.user["role"] == "admin")


def _current_user(request: Request, conn: sqlite3.Connection) -> dict | None:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    claims = decode_token(header[7:].strip(), request.app.state.settings.secret_key)
    if not claims:
        return None
    user = dbm.row(conn, "SELECT id, name, email, mobile, age, role, address, village, is_active, created_at FROM users WHERE id = ?", (int(claims["sub"]),))
    if not user or not user["is_active"]:
        return None
    return user


def endpoint(auth: str | None = "user", body: type[BaseModel] | None = None) -> Callable:
    """Decorator: opens a DB connection, authenticates, validates the body, maps errors to JSON.

    auth: None (public) | "user" (any signed-in user) | "admin".
    The wrapped handler has the signature ``handler(ctx, payload=None)``.
    Handlers may be written as plain `def` – Starlette will run them in a thread pool.
    """

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(request: Request) -> Response:
            settings = request.app.state.settings
            conn = dbm.connect(settings.database_path)
            try:
                user = _current_user(request, conn)
                if auth and not user:
                    raise ApiError(401, "Authentication required")
                if auth == "admin" and user and user["role"] != "admin":
                    raise ApiError(403, "Admin access required")
                ctx = Ctx(db=conn, user=user, settings=settings, request=request)
                payload = await parse(request, body) if body else None
                from starlette.concurrency import run_in_threadpool

                result = await run_in_threadpool(fn, ctx, payload) if body else await run_in_threadpool(fn, ctx)
                conn.commit()
                return result if isinstance(result, Response) else ok(result)
            except ApiError as exc:
                conn.rollback()
                return error_response(exc.status, exc.message, exc.details)
            except sqlite3.IntegrityError as exc:
                conn.rollback()
                return error_response(409, "Conflict: " + str(exc).split(":")[-1].strip())
            finally:
                conn.close()

        return wrapper

    return decorator


# --- tiny in-memory rate limiter (per process; use Redis for multi-instance deployments) ---
_attempts: dict[str, list[float]] = {}


def rate_limit(key: str, limit: int = 8, window: int = 300) -> None:
    now = time.time()
    recent = [t for t in _attempts.get(key, []) if now - t < window]
    if len(recent) >= limit:
        raise ApiError(429, "Too many attempts. Please wait a few minutes and try again.")
    recent.append(now)
    _attempts[key] = recent


def clear_rate_limit(key: str) -> None:
    _attempts.pop(key, None)


def reset_all_rate_limits() -> None:
    _attempts.clear()
