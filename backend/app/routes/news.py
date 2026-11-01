from __future__ import annotations

from starlette.responses import JSONResponse

from .. import ai as ai_mod
from .. import db as dbm
from ..http import ApiError, endpoint
from ..schemas import NewsDraftIn, NewsIn


def _item(ctx, nid: int) -> dict:
    n = dbm.row(ctx.db, "SELECT * FROM news WHERE id = ?", (nid,))
    if not n:
        raise ApiError(404, "News item not found")
    n["active"] = bool(n["active"])
    return n


@endpoint()
def list_news(ctx):
    qs = ctx.request.query_params
    where, params = [], []
    if not (ctx.is_admin and qs.get("all") == "1"):
        where.append("active = 1")
    if qs.get("category") in ("scheme", "deadline", "alert", "health", "general"):
        where.append("category = ?")
        params.append(qs["category"])
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    items = dbm.rows(ctx.db, f"SELECT * FROM news {clause} ORDER BY priority DESC, created_at DESC LIMIT 100", params)
    for n in items:
        n["active"] = bool(n["active"])
    return {"items": items}


_COLS = ("title", "description", "title_hi", "description_hi", "title_mr", "description_mr", "category", "priority", "active")


@endpoint(auth="admin", body=NewsIn)
def create_news(ctx, p: NewsIn):
    d = p.model_dump()
    nid = dbm.execute(ctx.db, f"INSERT INTO news ({', '.join(_COLS)}, created_by) VALUES ({', '.join('?' * len(_COLS))}, ?)", [int(d[c]) if c == "active" else d[c] for c in _COLS] + [ctx.user["id"]])
    dbm.audit(ctx.db, ctx.user["id"], "create", "news", nid, p.title)
    return JSONResponse(_item(ctx, nid), status_code=201)


@endpoint(auth="admin", body=NewsIn)
def update_news(ctx, p: NewsIn):
    nid = ctx.request.path_params["id"]
    _item(ctx, nid)
    d = p.model_dump()
    dbm.execute(ctx.db, f"UPDATE news SET {', '.join(c + ' = ?' for c in _COLS)} WHERE id = ?", [int(d[c]) if c == "active" else d[c] for c in _COLS] + [nid])
    dbm.audit(ctx.db, ctx.user["id"], "update", "news", nid, p.title)
    return _item(ctx, nid)


@endpoint(auth="admin")
def delete_news(ctx):
    nid = ctx.request.path_params["id"]
    _item(ctx, nid)
    dbm.execute(ctx.db, "DELETE FROM news WHERE id = ?", (nid,))
    dbm.audit(ctx.db, ctx.user["id"], "delete", "news", nid)
    return {"ok": True}


@endpoint(auth="admin", body=NewsDraftIn)
def draft(ctx, p: NewsDraftIn):
    return ai_mod.draft_news(ctx.request.app.state.ai, p.points)
