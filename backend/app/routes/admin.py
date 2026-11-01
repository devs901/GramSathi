"""Admin-only: user management, analytics dashboard, audit log, AI insights."""
from __future__ import annotations

from datetime import date, timedelta

from .. import ai as ai_mod
from .. import db as dbm
from ..http import ApiError, endpoint
from ..schemas import UserAdminUpdateIn


@endpoint(auth="admin")
def list_users(ctx):
    qs = ctx.request.query_params
    where, params = [], []
    if qs.get("role") in ("citizen", "admin"):
        where.append("role = ?")
        params.append(qs["role"])
    if qs.get("q"):
        where.append("(name LIKE ? OR email LIKE ? OR mobile LIKE ?)")
        params += [f"%{qs['q']}%"] * 3
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    try:
        limit, offset = min(int(qs.get("limit", 100)), 200), max(int(qs.get("offset", 0)), 0)
    except ValueError:
        raise ApiError(400, "limit/offset must be integers")
    total = dbm.scalar(ctx.db, f"SELECT COUNT(*) FROM users {clause}", params)
    items = dbm.rows(ctx.db, f"SELECT id, name, email, mobile, age, role, village, is_active, created_at FROM users {clause} ORDER BY id DESC LIMIT ? OFFSET ?", [*params, limit, offset])
    for u in items:
        u["is_active"] = bool(u["is_active"])
    return {"items": items, "total": total}


@endpoint(auth="admin", body=UserAdminUpdateIn)
def update_user(ctx, p: UserAdminUpdateIn):
    uid = ctx.request.path_params["id"]
    if uid == ctx.user["id"]:
        raise ApiError(409, "You cannot change your own role or active status")
    if not dbm.row(ctx.db, "SELECT 1 FROM users WHERE id = ?", (uid,)):
        raise ApiError(404, "User not found")
    if p.is_active is not None:
        dbm.execute(ctx.db, "UPDATE users SET is_active = ? WHERE id = ?", (int(p.is_active), uid))
    if p.role is not None:
        dbm.execute(ctx.db, "UPDATE users SET role = ? WHERE id = ?", (p.role, uid))
    dbm.audit(ctx.db, ctx.user["id"], "update", "user", uid, str(p.model_dump(exclude_none=True)))
    return {"ok": True}


def compute_stats(ctx) -> dict:
    db = ctx.db
    today = date.today()
    t, in30 = today.isoformat(), (today + timedelta(days=30)).isoformat()
    doc_counts = {r["status"]: r["n"] for r in dbm.rows(db, "SELECT status, COUNT(*) AS n FROM documents GROUP BY status")}
    trend = dbm.rows(
        db,
        "SELECT strftime('%Y-%m', created_at) AS month, COUNT(*) AS requests, "
        "SUM(status = 'approved') AS approved, SUM(status = 'rejected') AS rejected "
        "FROM documents GROUP BY month ORDER BY month DESC LIMIT 6",
    )[::-1]
    overdue_water = dbm.row(db, "SELECT COUNT(*) AS n, COALESCE(SUM(amount),0) AS amt FROM water_bills WHERE paid = 0 AND due_date < ?", (t,))
    overdue_prop = dbm.row(db, "SELECT COUNT(*) AS n, COALESCE(SUM(annual_tax),0) AS amt FROM properties WHERE paid = 0 AND due_date < ?", (t,))
    outstanding = (dbm.scalar(db, "SELECT COALESCE(SUM(amount),0) FROM water_bills WHERE paid = 0") or 0) + (dbm.scalar(db, "SELECT COALESCE(SUM(annual_tax),0) FROM properties WHERE paid = 0") or 0)
    collected = (dbm.scalar(db, "SELECT COALESCE(SUM(amount),0) FROM water_bills WHERE paid = 1") or 0) + (dbm.scalar(db, "SELECT COALESCE(SUM(annual_tax),0) FROM properties WHERE paid = 1") or 0)
    defaulters = dbm.rows(
        db,
        "SELECT u.id, u.name, SUM(d.amount) AS overdue_amount FROM ("
        "  SELECT w.user_id AS user_id, b.amount AS amount FROM water_bills b JOIN water_connections w ON w.id = b.connection_id WHERE b.paid = 0 AND b.due_date < ? "
        "  UNION ALL SELECT user_id, annual_tax FROM properties WHERE paid = 0 AND due_date < ?"
        ") d JOIN users u ON u.id = d.user_id GROUP BY u.id ORDER BY overdue_amount DESC LIMIT 5",
        (t, t),
    )
    per_center = dbm.rows(
        db,
        "SELECT c.name, COUNT(b.id) AS children FROM anganwadi_centers c "
        "LEFT JOIN anganwadi_beneficiaries b ON b.center_id = c.id AND b.status = 'active' GROUP BY c.id ORDER BY children DESC",
    )
    return {
        "citizens": {"total": dbm.scalar(db, "SELECT COUNT(*) FROM users WHERE role = 'citizen'"), "new_30d": dbm.scalar(db, "SELECT COUNT(*) FROM users WHERE role = 'citizen' AND created_at >= ?", ((today - timedelta(days=30)).isoformat(),))},
        "documents": {"pending": doc_counts.get("pending", 0), "approved": doc_counts.get("approved", 0), "rejected": doc_counts.get("rejected", 0), "trend": trend},
        "dues": {
            "overdue_count": overdue_water["n"] + overdue_prop["n"],
            "overdue_amount": overdue_water["amt"] + overdue_prop["amt"],
            "outstanding": outstanding,
            "collected": collected,
            "top_defaulters": defaulters,
        },
        "ration": {
            "active": dbm.scalar(db, "SELECT COUNT(*) FROM ration_cards WHERE status = 'active'"),
            "expiring_30d": dbm.scalar(db, "SELECT COUNT(*) FROM ration_cards WHERE status = 'active' AND validity_end BETWEEN ? AND ?", (t, in30)),
        },
        "anganwadi": {"centers": len(per_center), "active_children": sum(c["children"] for c in per_center), "per_center": per_center},
        "news": {"active": dbm.scalar(db, "SELECT COUNT(*) FROM news WHERE active = 1")},
    }


@endpoint(auth="admin")
def dashboard(ctx):
    return compute_stats(ctx)


@endpoint(auth="admin")
def insights(ctx):
    return ai_mod.insights(ctx.request.app.state.ai, compute_stats(ctx))


@endpoint(auth="admin")
def audit_log(ctx):
    return {"items": dbm.rows(ctx.db, "SELECT a.*, u.name AS actor FROM audit_log a LEFT JOIN users u ON u.id = a.actor_id ORDER BY a.id DESC LIMIT 100")}
