from __future__ import annotations

from datetime import date

from .. import ai as ai_mod
from .. import db as dbm
from ..http import endpoint
from ..schemas import ChatIn


def build_context(ctx) -> dict:
    """Collect ONLY the signed-in citizen's own records for the model (data minimisation)."""
    db, uid = ctx.db, ctx.user["id"]
    cards = dbm.rows(db, "SELECT * FROM ration_cards WHERE user_id = ? ORDER BY id DESC LIMIT 1", (uid,))
    ration = None
    if cards:
        ration = {**{k: cards[0][k] for k in ("card_no", "card_type", "status", "validity_end", "distribution_point")},
                  "items": dbm.rows(db, "SELECT name, quantity, unit FROM ration_items WHERE card_id = ?", (cards[0]["id"],))}
    dues = dbm.rows(
        db,
        "SELECT 'Water bill ' || b.period AS label, b.amount AS amount, b.due_date AS due_date FROM water_bills b JOIN water_connections w ON w.id = b.connection_id WHERE w.user_id = ? AND b.paid = 0 "
        "UNION ALL SELECT 'Property tax ' || property_no, annual_tax, due_date FROM properties WHERE user_id = ? AND paid = 0 ORDER BY due_date",
        (uid, uid),
    )
    for d in dues:
        d["overdue"] = d["due_date"] < date.today().isoformat()
    return {
        "today": date.today().isoformat(),
        "citizen": {"name": ctx.user["name"], "village": ctx.user["village"]},
        "ration": ration,
        "dues": dues,
        "documents": dbm.rows(db, "SELECT id, doc_type, status, admin_note FROM documents WHERE user_id = ? ORDER BY id DESC LIMIT 5", (uid,)),
        "anganwadi": dbm.rows(db, "SELECT b.child_name, b.status, c.name AS center FROM anganwadi_beneficiaries b JOIN anganwadi_centers c ON c.id = b.center_id WHERE b.user_id = ?", (uid,)),
        "news": dbm.rows(db, "SELECT title, category FROM news WHERE active = 1 ORDER BY priority DESC, created_at DESC LIMIT 5"),
    }


@endpoint(body=ChatIn)
def chat(ctx, p: ChatIn):
    history = dbm.rows(ctx.db, "SELECT role, content FROM chat_messages WHERE user_id = ? ORDER BY id DESC LIMIT 8", (ctx.user["id"],))[::-1]
    result = ai_mod.chat(ctx.request.app.state.ai, p.message, build_context(ctx), history, p.language)
    dbm.execute(ctx.db, "INSERT INTO chat_messages (user_id, role, content, source) VALUES (?, 'user', ?, ?)", (ctx.user["id"], p.message, result["source"]))
    dbm.execute(ctx.db, "INSERT INTO chat_messages (user_id, role, content, source) VALUES (?, 'assistant', ?, ?)", (ctx.user["id"], result["reply"], result["source"]))
    return result


@endpoint()
def history(ctx):
    items = dbm.rows(ctx.db, "SELECT role, content, source, created_at FROM chat_messages WHERE user_id = ? ORDER BY id DESC LIMIT 40", (ctx.user["id"],))[::-1]
    return {"items": items}
