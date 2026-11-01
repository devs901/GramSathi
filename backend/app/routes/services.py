"""Citizen services: ration, anganwadi, water tax, property tax."""
from __future__ import annotations

import json
import math
from datetime import date

from starlette.responses import JSONResponse

from .. import db as dbm
from ..http import ApiError, endpoint
from ..schemas import BeneficiaryIn, CenterIn, PropertyIn, RationIn, WaterBillIn


# ----------------------------------------------------------------------------- ration
def _cards(ctx, where: str = "", params: tuple = ()) -> list[dict]:
    cards = dbm.rows(
        ctx.db,
        f"SELECT r.*, u.name AS holder_name, u.email AS holder_email FROM ration_cards r JOIN users u ON u.id = r.user_id {where} ORDER BY r.id DESC",
        params,
    )
    for c in cards:
        c["items"] = dbm.rows(ctx.db, "SELECT name, quantity, unit FROM ration_items WHERE card_id = ?", (c["id"],))
    return cards


@endpoint()
def my_ration(ctx):
    return {"items": _cards(ctx, "WHERE r.user_id = ?", (ctx.user["id"],))}


@endpoint(auth="admin")
def admin_ration(ctx):
    return {"items": _cards(ctx)}


def _require_user(ctx, user_id: int) -> None:
    if not dbm.row(ctx.db, "SELECT 1 FROM users WHERE id = ?", (user_id,)):
        raise ApiError(422, "user_id does not exist", [{"field": "user_id", "message": "unknown user"}])


def _save_ration(ctx, p: RationIn, card_id: int | None):
    _require_user(ctx, p.user_id)
    vals = (p.user_id, p.card_no, p.card_type, p.validity_start.isoformat(), p.validity_end.isoformat(), p.distribution_point, p.status)
    if card_id is None:
        card_id = dbm.execute(ctx.db, "INSERT INTO ration_cards (user_id, card_no, card_type, validity_start, validity_end, distribution_point, status) VALUES (?,?,?,?,?,?,?)", vals)
    else:
        if not dbm.row(ctx.db, "SELECT 1 FROM ration_cards WHERE id = ?", (card_id,)):
            raise ApiError(404, "Ration card not found")
        dbm.execute(ctx.db, "UPDATE ration_cards SET user_id=?, card_no=?, card_type=?, validity_start=?, validity_end=?, distribution_point=?, status=? WHERE id=?", vals + (card_id,))
        dbm.execute(ctx.db, "DELETE FROM ration_items WHERE card_id = ?", (card_id,))
    for it in p.items:
        dbm.execute(ctx.db, "INSERT INTO ration_items (card_id, name, quantity, unit) VALUES (?,?,?,?)", (card_id, it.name, it.quantity, it.unit))
    dbm.audit(ctx.db, ctx.user["id"], "save", "ration_card", card_id, p.card_no)
    return _cards(ctx, "WHERE r.id = ?", (card_id,))[0]


@endpoint(auth="admin", body=RationIn)
def create_ration(ctx, p: RationIn):
    return JSONResponse(_save_ration(ctx, p, None), status_code=201)


@endpoint(auth="admin", body=RationIn)
def update_ration(ctx, p: RationIn):
    return _save_ration(ctx, p, ctx.request.path_params["id"])


# ------------------------------------------------------------------------- anganwadi
def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _center(c: dict) -> dict:
    c["services"] = dbm.loads(c["services"], [])
    return c


@endpoint()
def list_centers(ctx):
    qs = ctx.request.query_params
    centers = [_center(c) for c in dbm.rows(
        ctx.db,
        "SELECT c.*, COUNT(CASE WHEN b.status = 'active' THEN 1 END) AS active_children "
        "FROM anganwadi_centers c LEFT JOIN anganwadi_beneficiaries b ON b.center_id = c.id GROUP BY c.id ORDER BY c.name",
    )]
    try:
        lat, lng = float(qs["lat"]), float(qs["lng"])
    except (KeyError, ValueError):
        return {"items": centers}
    for c in centers:
        c["distance_km"] = round(_haversine_km(lat, lng, c["latitude"], c["longitude"]), 2)
    return {"items": sorted(centers, key=lambda c: c["distance_km"])}


def _save_center(ctx, p: CenterIn, cid: int | None):
    vals = (p.name, p.address, p.phone, p.latitude, p.longitude, json.dumps(p.services), p.open_time, p.close_time)
    if cid is None:
        cid = dbm.execute(ctx.db, "INSERT INTO anganwadi_centers (name,address,phone,latitude,longitude,services,open_time,close_time) VALUES (?,?,?,?,?,?,?,?)", vals)
    else:
        if not dbm.row(ctx.db, "SELECT 1 FROM anganwadi_centers WHERE id = ?", (cid,)):
            raise ApiError(404, "Center not found")
        dbm.execute(ctx.db, "UPDATE anganwadi_centers SET name=?,address=?,phone=?,latitude=?,longitude=?,services=?,open_time=?,close_time=? WHERE id=?", vals + (cid,))
    dbm.audit(ctx.db, ctx.user["id"], "save", "anganwadi_center", cid, p.name)
    return _center(dbm.row(ctx.db, "SELECT * FROM anganwadi_centers WHERE id = ?", (cid,)))


@endpoint(auth="admin", body=CenterIn)
def create_center(ctx, p: CenterIn):
    return JSONResponse(_save_center(ctx, p, None), status_code=201)


@endpoint(auth="admin", body=CenterIn)
def update_center(ctx, p: CenterIn):
    return _save_center(ctx, p, ctx.request.path_params["id"])


_BENEFICIARY_SQL = (
    "SELECT b.*, c.name AS center, u.name AS guardian FROM anganwadi_beneficiaries b "
    "JOIN anganwadi_centers c ON c.id = b.center_id JOIN users u ON u.id = b.user_id "
)


@endpoint()
def my_anganwadi(ctx):
    return {"items": dbm.rows(ctx.db, _BENEFICIARY_SQL + "WHERE b.user_id = ? ORDER BY b.id", (ctx.user["id"],))}


@endpoint(auth="admin")
def admin_beneficiaries(ctx):
    return {"items": dbm.rows(ctx.db, _BENEFICIARY_SQL + "ORDER BY b.id DESC LIMIT 300")}


@endpoint(auth="admin", body=BeneficiaryIn)
def create_beneficiary(ctx, p: BeneficiaryIn):
    _require_user(ctx, p.user_id)
    if not dbm.row(ctx.db, "SELECT 1 FROM anganwadi_centers WHERE id = ?", (p.center_id,)):
        raise ApiError(422, "center_id does not exist", [{"field": "center_id", "message": "unknown center"}])
    bid = dbm.execute(ctx.db, "INSERT INTO anganwadi_beneficiaries (user_id, center_id, child_name, age_group, status, enrollment_date) VALUES (?,?,?,?,?,?)",
                      (p.user_id, p.center_id, p.child_name, p.age_group, p.status, p.enrollment_date.isoformat()))
    dbm.audit(ctx.db, ctx.user["id"], "create", "beneficiary", bid, p.child_name)
    return JSONResponse(dbm.row(ctx.db, _BENEFICIARY_SQL + "WHERE b.id = ?", (bid,)), status_code=201)


# ---------------------------------------------------------------------------- taxes
def _water(ctx, where: str, params: tuple) -> list[dict]:
    conns = dbm.rows(ctx.db, f"SELECT w.*, u.name AS holder_name FROM water_connections w JOIN users u ON u.id = w.user_id {where}", params)
    for c in conns:
        c["bills"] = [{**b, "paid": bool(b["paid"])} for b in dbm.rows(ctx.db, "SELECT * FROM water_bills WHERE connection_id = ? ORDER BY period DESC", (c["id"],))]
    return conns


def _properties(ctx, where: str = "", params: tuple = ()) -> list[dict]:
    props = dbm.rows(ctx.db, f"SELECT p.*, u.name AS holder_name FROM properties p JOIN users u ON u.id = p.user_id {where} ORDER BY p.id DESC", params)
    for p in props:
        p["paid"] = bool(p["paid"])
    return props


@endpoint()
def my_water(ctx):
    return {"items": _water(ctx, "WHERE w.user_id = ?", (ctx.user["id"],))}


@endpoint()
def my_property(ctx):
    return {"items": _properties(ctx, "WHERE p.user_id = ?", (ctx.user["id"],))}


@endpoint(auth="admin")
def admin_water(ctx):
    return {"items": _water(ctx, "", ())}


@endpoint(auth="admin")
def admin_property(ctx):
    return {"items": _properties(ctx)}


@endpoint(auth="admin", body=WaterBillIn)
def upsert_water_bill(ctx, p: WaterBillIn):
    _require_user(ctx, p.user_id)
    conn = dbm.row(ctx.db, "SELECT id, user_id FROM water_connections WHERE connection_no = ?", (p.connection_no,))
    if conn and conn["user_id"] != p.user_id:
        raise ApiError(409, "Connection number belongs to a different citizen")
    cid = conn["id"] if conn else dbm.execute(ctx.db, "INSERT INTO water_connections (user_id, connection_no) VALUES (?, ?)", (p.user_id, p.connection_no))
    dbm.execute(
        ctx.db,
        "INSERT INTO water_bills (connection_id, period, amount, due_date) VALUES (?,?,?,?) "
        "ON CONFLICT(connection_id, period) DO UPDATE SET amount = excluded.amount, due_date = excluded.due_date",
        (cid, p.period, p.amount, p.due_date.isoformat()),
    )
    dbm.audit(ctx.db, ctx.user["id"], "save", "water_bill", cid, f"{p.connection_no} {p.period}")
    return JSONResponse(_water(ctx, "WHERE w.id = ?", (cid,))[0], status_code=201)


@endpoint(auth="admin", body=PropertyIn)
def create_property(ctx, p: PropertyIn):
    _require_user(ctx, p.user_id)
    annual = round(p.value * p.tax_rate / 100, 2)  # computed server-side; never trust a client-sent total
    pid = dbm.execute(ctx.db, "INSERT INTO properties (user_id, property_no, address, area_sqft, value, tax_rate, annual_tax, due_date) VALUES (?,?,?,?,?,?,?,?)",
                      (p.user_id, p.property_no, p.address, p.area_sqft, p.value, p.tax_rate, annual, p.due_date.isoformat()))
    dbm.audit(ctx.db, ctx.user["id"], "create", "property", pid, p.property_no)
    return JSONResponse(_properties(ctx, "WHERE p.id = ?", (pid,))[0], status_code=201)


@endpoint()
def pay_water_bill(ctx):
    bill_id = ctx.request.path_params["id"]
    bill = dbm.row(ctx.db, "SELECT b.*, w.user_id FROM water_bills b JOIN water_connections w ON w.id = b.connection_id WHERE b.id = ?", (bill_id,))
    if not bill or bill["user_id"] != ctx.user["id"]:
        raise ApiError(404, "Bill not found")
    if bill["paid"]:
        raise ApiError(409, "Bill is already paid")
    dbm.execute(ctx.db, "UPDATE water_bills SET paid = 1, paid_on = ? WHERE id = ?", (date.today().isoformat(), bill_id))
    dbm.audit(ctx.db, ctx.user["id"], "pay", "water_bill", bill_id, f"{bill['amount']}")
    return {"ok": True, "simulated": True, "note": "Simulated payment. Plug a gateway (e.g. Razorpay/UPI) in before going live."}


@endpoint()
def pay_property(ctx):
    pid = ctx.request.path_params["id"]
    prop = dbm.row(ctx.db, "SELECT * FROM properties WHERE id = ? AND user_id = ?", (pid, ctx.user["id"]))
    if not prop:
        raise ApiError(404, "Property not found")
    if prop["paid"]:
        raise ApiError(409, "Property tax is already paid")
    dbm.execute(ctx.db, "UPDATE properties SET paid = 1, last_paid = ? WHERE id = ?", (date.today().isoformat(), pid))
    dbm.audit(ctx.db, ctx.user["id"], "pay", "property", pid, f"{prop['annual_tax']}")
    return {"ok": True, "simulated": True, "note": "Simulated payment. Plug a gateway (e.g. Razorpay/UPI) in before going live."}
