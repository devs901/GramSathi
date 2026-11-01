from __future__ import annotations

import json

from starlette.responses import JSONResponse, Response

from .. import ai as ai_mod
from .. import db as dbm
from ..http import ApiError, endpoint
from ..pdf import certificate_pdf
from ..schemas import DocumentIn, ReviewIn


def _present(d: dict) -> dict:
    d["data"] = dbm.loads(d["data"], {})
    d["ai_review"] = dbm.loads(d.get("ai_review"))
    return d


def _load(ctx, doc_id: int) -> dict:
    d = dbm.row(
        ctx.db,
        "SELECT d.*, u.name AS applicant_name, u.email AS applicant_email FROM documents d JOIN users u ON u.id = d.user_id WHERE d.id = ?",
        (doc_id,),
    )
    if not d or (not ctx.is_admin and d["user_id"] != ctx.user["id"]):
        raise ApiError(404, "Document request not found")  # 404 (not 403) so IDs of others are not revealed
    return _present(d)


@endpoint(body=DocumentIn)
def create(ctx, p: DocumentIn):
    data = p.model_dump(mode="json", exclude={"doc_type"})
    duplicates = dbm.scalar(
        ctx.db,
        "SELECT COUNT(*) FROM documents WHERE user_id = ? AND doc_type = ? AND status IN ('pending','approved') "
        "AND json_extract(data, '$.full_name') = ? AND json_extract(data, '$.date_of_birth') = ?",
        (ctx.user["id"], p.doc_type, data["full_name"], data["date_of_birth"]),
    )
    review = ai_mod.review_document(ctx.request.app.state.ai, p.doc_type, data, ctx.user, duplicates)
    doc_id = dbm.execute(
        ctx.db,
        "INSERT INTO documents (user_id, doc_type, data, ai_review) VALUES (?, ?, ?, ?)",
        (ctx.user["id"], p.doc_type, json.dumps(data), json.dumps(review)),
    )
    dbm.audit(ctx.db, ctx.user["id"], "create", "document", doc_id, p.doc_type)
    return JSONResponse(_load(ctx, doc_id), status_code=201)


@endpoint()
def list_documents(ctx):
    qs = ctx.request.query_params
    where, params = [], []
    if not ctx.is_admin:
        where.append("d.user_id = ?")
        params.append(ctx.user["id"])
    if qs.get("status") in ("pending", "approved", "rejected"):
        where.append("d.status = ?")
        params.append(qs["status"])
    if ctx.is_admin and qs.get("q"):
        where.append("(u.name LIKE ? OR u.email LIKE ?)")
        params += [f"%{qs['q']}%"] * 2
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    items = dbm.rows(
        ctx.db,
        f"SELECT d.*, u.name AS applicant_name, u.email AS applicant_email FROM documents d JOIN users u ON u.id = d.user_id {clause} "
        "ORDER BY CASE d.status WHEN 'pending' THEN 0 ELSE 1 END, d.created_at DESC LIMIT 200",
        params,
    )
    return {"items": [_present(i) for i in items]}


@endpoint()
def get_document(ctx):
    return _load(ctx, ctx.request.path_params["id"])


@endpoint(auth="admin", body=ReviewIn)
def review(ctx, p: ReviewIn):
    doc = _load(ctx, ctx.request.path_params["id"])
    if doc["status"] != "pending":
        raise ApiError(409, f"Request was already {doc['status']}")
    if p.decision == "rejected" and not p.note.strip():
        raise ApiError(422, "A reason is required when rejecting a request", [{"field": "note", "message": "required for rejection"}])
    dbm.execute(
        ctx.db,
        "UPDATE documents SET status = ?, admin_note = ?, reviewed_by = ?, reviewed_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = ?",
        (p.decision, p.note.strip(), ctx.user["id"], doc["id"]),
    )
    dbm.audit(ctx.db, ctx.user["id"], p.decision, "document", doc["id"], p.note)
    return _load(ctx, doc["id"])


@endpoint()
def download_pdf(ctx):
    doc = _load(ctx, ctx.request.path_params["id"])
    if doc["status"] != "approved":
        raise ApiError(409, "Certificate is available only after approval")
    pdf = certificate_pdf(doc)
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="gramsathi-{doc["id"]}.pdf"'})
