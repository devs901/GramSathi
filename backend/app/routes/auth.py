from __future__ import annotations

from .. import db as dbm
from ..http import ApiError, clear_rate_limit, endpoint, rate_limit
from ..schemas import LoginIn, ProfileUpdateIn, RegisterIn
from ..security import create_token, hash_password, verify_password

_DUMMY_HASH = hash_password("not-a-real-password-1")
_PUBLIC_COLS = "id, name, email, mobile, age, role, address, village, created_at"


def _session(ctx, user: dict) -> dict:
    token = create_token(user["id"], user["role"], ctx.settings.secret_key, ctx.settings.token_ttl_minutes)
    return {"token": token, "user": {k: user[k] for k in ("id", "name", "email", "mobile", "age", "role", "address", "village")}}


def _client_ip(ctx) -> str:
    return ctx.request.client.host if ctx.request.client else "unknown"


@endpoint(auth=None, body=RegisterIn)
def register(ctx, p: RegisterIn):
    rate_limit("register:" + _client_ip(ctx), limit=10, window=3600)
    if dbm.row(ctx.db, "SELECT 1 FROM users WHERE email = ?", (p.email,)):
        raise ApiError(409, "An account with this email already exists")
    uid = dbm.execute(
        ctx.db,
        "INSERT INTO users (name, email, mobile, age, role, address, village, password_hash) VALUES (?, ?, ?, ?, 'citizen', ?, ?, ?)",
        (p.name.strip(), p.email.lower(), p.mobile, p.age, p.address, p.village, hash_password(p.password)),
    )
    dbm.audit(ctx.db, uid, "register", "user", uid)
    user = dbm.row(ctx.db, f"SELECT {_PUBLIC_COLS} FROM users WHERE id = ?", (uid,))
    from starlette.responses import JSONResponse

    return JSONResponse(_session(ctx, user), status_code=201)


@endpoint(auth=None, body=LoginIn)
def login(ctx, p: LoginIn):
    key = f"login:{_client_ip(ctx)}:{p.email.lower()}"
    rate_limit(key)
    user = dbm.row(ctx.db, f"SELECT {_PUBLIC_COLS}, password_hash, is_active FROM users WHERE email = ?", (p.email.lower(),))
    valid = verify_password(p.password, user["password_hash"] if user else _DUMMY_HASH)
    if not user or not valid or not user["is_active"]:
        raise ApiError(401, "Invalid email or password")
    clear_rate_limit(key)
    return _session(ctx, user)


@endpoint()
def me(ctx):
    return {"user": ctx.user}


@endpoint(body=ProfileUpdateIn)
def update_me(ctx, p: ProfileUpdateIn):
    changes = p.model_dump(exclude_none=True)
    if changes:
        allowed = {"name", "address", "village", "mobile"}  # whitelist of column names
        sets = ", ".join(f"{k} = ?" for k in changes if k in allowed)
        dbm.execute(ctx.db, f"UPDATE users SET {sets}, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = ?", [*changes.values(), ctx.user["id"]])
    return {"user": dbm.row(ctx.db, f"SELECT {_PUBLIC_COLS} FROM users WHERE id = ?", (ctx.user["id"],))}
