from datetime import date, timedelta

from .conftest import DOC, login


# ------------------------------------------------------------------ auth
def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json() == {"status": "ok", "ai": "rules"}


def test_register_validation_and_duplicate(client):
    bad = client.post("/api/auth/register", json={"name": "A", "email": "nope", "mobile": "123", "age": 0, "password": "short"})
    assert bad.status_code == 422
    fields = {d["field"] for d in bad.json()["details"]}
    assert {"name", "email", "mobile", "age", "password"} <= fields

    good = {"name": "New Citizen", "email": "new@example.com", "mobile": "+91 98765 43210", "age": 30, "password": "Passw0rd123"}
    r = client.post("/api/auth/register", json=good)
    assert r.status_code == 201 and r.json()["user"]["role"] == "citizen" and r.json()["user"]["mobile"] == "9876543210"
    assert "password" not in str(r.json()).lower().replace("password_hash", "x") or "password_hash" not in r.text
    assert client.post("/api/auth/register", json=good).status_code == 409


def test_cannot_self_register_as_admin(client):
    r = client.post("/api/auth/register", json={"name": "Evil", "email": "e@example.com", "mobile": "9876543210", "age": 30, "password": "Passw0rd123", "role": "admin"})
    assert r.status_code == 201 and r.json()["user"]["role"] == "citizen"


def test_login_and_me(client):
    assert client.post("/api/auth/login", json={"email": "ramesh@example.com", "password": "wrong"}).status_code == 401
    h = login(client, ("RAMESH@example.com", "Citizen@1234"))  # email is case-insensitive
    me = client.get("/api/auth/me", headers=h).json()["user"]
    assert me["email"] == "ramesh@example.com" and "password_hash" not in me


def test_login_rate_limit(client):
    for _ in range(8):
        client.post("/api/auth/login", json={"email": "ramesh@example.com", "password": "bad"})
    assert client.post("/api/auth/login", json={"email": "ramesh@example.com", "password": "Citizen@1234"}).status_code == 429


def test_auth_required_and_roles(client, citizen):
    assert client.get("/api/documents").status_code == 401
    assert client.get("/api/documents", headers={"Authorization": "Bearer garbage"}).status_code == 401
    assert client.get("/api/admin/dashboard", headers=citizen).status_code == 403
    assert client.get("/api/admin/users", headers=citizen).status_code == 403


def test_profile_update(client, citizen):
    r = client.patch("/api/auth/me", headers=citizen, json={"village": "Ozar", "role": "admin"})
    assert r.status_code == 200 and r.json()["user"]["village"] == "Ozar" and r.json()["user"]["role"] == "citizen"


def test_admin_cannot_deactivate_self_and_deactivated_cannot_login(client, admin):
    me = client.get("/api/auth/me", headers=admin).json()["user"]
    assert client.patch(f"/api/admin/users/{me['id']}", headers=admin, json={"is_active": False}).status_code == 409
    users = client.get("/api/admin/users?q=meena", headers=admin).json()["items"]
    assert client.patch(f"/api/admin/users/{users[0]['id']}", headers=admin, json={"is_active": False}).status_code == 200
    assert client.post("/api/auth/login", json={"email": "meena@example.com", "password": "Citizen@1234"}).status_code == 401


def test_sql_injection_in_search_is_inert(client, admin):
    r = client.get("/api/admin/users", params={"q": "' OR 1=1; DROP TABLE users;--"}, headers=admin)
    assert r.status_code == 200 and r.json()["items"] == []
    assert client.get("/api/admin/users", headers=admin).json()["total"] >= 5


# ------------------------------------------------------------------ documents
def test_document_lifecycle(client, citizen, admin, other):
    r = client.post("/api/documents", headers=citizen, json=DOC)
    assert r.status_code == 201
    doc = r.json()
    assert doc["status"] == "pending" and doc["ai_review"]["source"] == "rules" and doc["ai_review"]["risk_level"] == "low"

    assert client.get(f"/api/documents/{doc['id']}", headers=other).status_code == 404  # not yours
    assert client.get(f"/api/documents/{doc['id']}/pdf", headers=citizen).status_code == 409  # not approved yet
    assert client.post(f"/api/documents/{doc['id']}/review", headers=citizen, json={"decision": "approved"}).status_code == 403
    assert client.post(f"/api/documents/{doc['id']}/review", headers=admin, json={"decision": "rejected"}).status_code == 422

    ok = client.post(f"/api/documents/{doc['id']}/review", headers=admin, json={"decision": "approved", "note": "Verified"})
    assert ok.status_code == 200 and ok.json()["status"] == "approved"
    assert client.post(f"/api/documents/{doc['id']}/review", headers=admin, json={"decision": "rejected", "note": "x"}).status_code == 409

    pdf = client.get(f"/api/documents/{doc['id']}/pdf", headers=citizen)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF") and pdf.headers["content-type"] == "application/pdf"
    assert client.get(f"/api/documents/{doc['id']}/pdf", headers=other).status_code == 404

    mine = client.get("/api/documents", headers=citizen).json()["items"]
    assert all(d["user_id"] == doc["user_id"] for d in mine)


def test_document_validation_and_ai_flags(client, citizen):
    future = (date.today() + timedelta(days=5)).isoformat()
    assert client.post("/api/documents", headers=citizen, json={**DOC, "date_of_birth": future}).status_code == 422
    assert client.post("/api/documents", headers=citizen, json={**DOC, "doc_type": "passport"}).status_code == 422

    risky = {**DOC, "full_name": "Zed Unknown", "father_name": "Someone Else", "mother_name": "", "place_of_birth": "", "address": "see http://evil.example/x"}
    review = client.post("/api/documents", headers=citizen, json=risky).json()["ai_review"]
    assert review["risk_level"] in ("medium", "high") and review["flags"]

    dup = client.post("/api/documents", headers=citizen, json=DOC)  # first of its kind...
    dup2 = client.post("/api/documents", headers=citizen, json=DOC)  # ...second is a duplicate
    assert any("same person" in f for f in dup2.json()["ai_review"]["flags"]) and dup.status_code == 201


def test_document_ai_review_uses_claude_when_available(ai_client, fake_ai):
    fake_ai.reply = '{"summary": "Looks consistent; father name matches the applicant.", "extra_flags": ["Check hospital record"]}'
    h = login(ai_client, ("ramesh@example.com", "Citizen@1234"))
    review = ai_client.post("/api/documents", headers=h, json=DOC).json()["ai_review"]
    assert review["source"] == "claude" and "consistent" in review["summary"] and "Check hospital record" in review["flags"]
    assert "untrusted" in fake_ai.calls[0]["system"]


# ------------------------------------------------------------------ news
def test_news_permissions_and_crud(client, citizen, admin):
    item = {"title": "Water supply cut", "description": "No water on Monday 10 AM to 2 PM.", "category": "alert", "priority": 5}
    assert client.post("/api/news", headers=citizen, json=item).status_code == 403
    created = client.post("/api/news", headers=admin, json=item)
    assert created.status_code == 201
    nid = created.json()["id"]
    feed = client.get("/api/news", headers=citizen).json()["items"]
    assert feed[0]["id"] == nid  # priority 5 sorts first
    assert client.put(f"/api/news/{nid}", headers=admin, json={**item, "active": False}).status_code == 200
    assert nid not in [n["id"] for n in client.get("/api/news", headers=citizen).json()["items"]]
    assert nid in [n["id"] for n in client.get("/api/news?all=1", headers=admin).json()["items"]]
    assert client.delete(f"/api/news/{nid}", headers=admin).status_code == 200
    assert client.delete(f"/api/news/{nid}", headers=admin).status_code == 404
    assert client.post("/api/news", headers=admin, json={**item, "priority": 9}).status_code == 422


def test_news_draft_rules_and_claude(client, admin, ai_client, fake_ai):
    d = client.post("/api/ai/news-draft", headers=admin, json={"points": "Free dengue vaccination camp Sunday 9am at panchayat hall"}).json()
    assert d["source"] == "rules" and d["category"] == "health"

    h = login(ai_client, ("admin@gramsathi.in", "Admin@1234"))
    fake_ai.reply = 'Sure! {"title": "Health camp on Sunday", "description": "A free camp is on Sunday at 9 AM.", "category": "health", "priority": 3, "title_hi": "स्वास्थ्य शिविर", "description_hi": "रविवार को शिविर", "title_mr": "आरोग्य शिबिर", "description_mr": "रविवारी शिबिर"}'
    d = ai_client.post("/api/ai/news-draft", headers=h, json={"points": "health camp sunday 9am"}).json()
    assert d["source"] == "claude" and d["title_hi"] == "स्वास्थ्य शिविर" and d["title_mr"] == "आरोग्य शिबिर"

    fake_ai.reply = "I cannot do that"  # unusable model output -> graceful fallback
    d = ai_client.post("/api/ai/news-draft", headers=h, json={"points": "health camp sunday 9am"}).json()
    assert d["source"] == "rules"


def test_ai_failure_falls_back(tmp_path):
    from starlette.testclient import TestClient
    from app import ai as ai_mod
    from app.main import create_app
    from .conftest import make_settings

    def boom(body):
        raise OSError("network down")

    app = create_app(make_settings(tmp_path), ai_mod.AIClient(make_settings(tmp_path), transport=boom))
    with TestClient(app) as c:
        h = login(c, ("admin@gramsathi.in", "Admin@1234"))
        r = c.post("/api/admin/ai/insights", headers=h)
        assert r.status_code == 200 and r.json()["source"] == "rules"


# ------------------------------------------------------------------ ration / anganwadi / taxes
def test_ration_admin_and_citizen_scope(client, citizen, admin):
    mine = client.get("/api/me/ration", headers=citizen).json()["items"]
    assert len(mine) == 1 and mine[0]["card_no"] == "MH-RC-1001" and len(mine[0]["items"]) == 4
    assert client.get("/api/admin/ration", headers=citizen).status_code == 403
    assert len(client.get("/api/admin/ration", headers=admin).json()["items"]) == 3

    uid = client.get("/api/admin/users?q=meena", headers=admin).json()["items"][0]["id"]
    payload = {"user_id": uid, "card_no": "MH-RC-9999", "card_type": "BPL", "validity_start": "2026-01-01", "validity_end": "2027-01-01",
               "items": [{"name": "Rice", "quantity": 5, "unit": "kg"}]}
    assert client.post("/api/admin/ration", headers=admin, json=payload).status_code == 201
    assert client.post("/api/admin/ration", headers=admin, json=payload).status_code == 409  # duplicate card_no
    assert client.post("/api/admin/ration", headers=admin, json={**payload, "card_no": "X-1234", "validity_end": "2025-01-01"}).status_code == 422
    assert client.post("/api/admin/ration", headers=admin, json={**payload, "card_no": "X-1235", "user_id": 9999}).status_code == 422


def test_anganwadi_nearby_sorted(client, citizen):
    items = client.get("/api/anganwadi?lat=20.0125&lng=73.7551", headers=citizen).json()["items"]
    assert items[0]["name"].startswith("Anganwadi Center 2") and items[0]["distance_km"] < items[1]["distance_km"]
    assert isinstance(items[0]["services"], list)
    assert "distance_km" not in client.get("/api/anganwadi?lat=abc&lng=1", headers=citizen).json()["items"][0]


def test_property_tax_computed_server_side_and_payment_ownership(client, admin, citizen, other):
    uid = client.get("/api/auth/me", headers=citizen).json()["user"]["id"]
    r = client.post("/api/admin/property", headers=admin, json={"user_id": uid, "property_no": "PT-7777", "address": "Plot 9", "area_sqft": 900, "value": 1000000, "tax_rate": 0.5, "due_date": "2027-03-31", "annual_tax": 1})
    assert r.status_code == 201 and r.json()["annual_tax"] == 5000.0
    pid = r.json()["id"]
    assert client.post(f"/api/me/property/{pid}/pay", headers=other).status_code == 404
    assert client.post(f"/api/me/property/{pid}/pay", headers=citizen).json()["simulated"] is True
    assert client.post(f"/api/me/property/{pid}/pay", headers=citizen).status_code == 409


def test_water_bill_upsert_and_pay(client, admin, citizen):
    uid = client.get("/api/auth/me", headers=citizen).json()["user"]["id"]
    body = {"user_id": uid, "connection_no": "WC-2001", "period": "2099-01", "amount": 250, "due_date": "2099-02-10"}
    assert client.post("/api/admin/water/bills", headers=admin, json=body).status_code == 201
    assert client.post("/api/admin/water/bills", headers=admin, json={**body, "amount": 300}).status_code == 201  # upsert, no duplicate
    conn = client.get("/api/me/water", headers=citizen).json()["items"][0]
    new = [b for b in conn["bills"] if b["period"] == "2099-01"]
    assert len(new) == 1 and new[0]["amount"] == 300
    assert client.post("/api/admin/water/bills", headers=admin, json={**body, "user_id": uid + 1}).status_code == 409
    assert client.post(f"/api/me/water/bills/{new[0]['id']}/pay", headers=citizen).status_code == 200
    assert client.post("/api/admin/water/bills", headers=admin, json={**body, "period": "2099-13"}).status_code == 422


# ------------------------------------------------------------------ dashboard & audit
def test_dashboard_and_insights(client, admin):
    s = client.get("/api/admin/dashboard", headers=admin).json()
    assert s["citizens"]["total"] == 4 and s["documents"]["pending"] == 2 and s["documents"]["approved"] == 1
    assert s["dues"]["overdue_count"] >= 1 and s["dues"]["top_defaulters"][0]["overdue_amount"] > 0
    assert s["ration"]["expiring_30d"] == 1 and s["anganwadi"]["active_children"] == 3
    ins = client.post("/api/admin/ai/insights", headers=admin).json()
    assert ins["source"] == "rules" and any("waiting for review" in i for i in ins["items"])


def test_audit_log_records_actions(client, admin, citizen):
    d = client.post("/api/documents", headers=citizen, json=DOC).json()
    client.post(f"/api/documents/{d['id']}/review", headers=admin, json={"decision": "approved"})
    log = client.get("/api/admin/audit", headers=admin).json()["items"]
    assert {"create", "approved"} <= {e["action"] for e in log if e["entity"] == "document"}


# ------------------------------------------------------------------ assistant
def test_chat_rules_mode_uses_own_data(client, citizen):
    r = client.post("/api/ai/chat", headers=citizen, json={"message": "What is my ration entitlement?"}).json()
    assert r["source"] == "rules" and "BPL" in r["reply"] and "Wheat" in r["reply"]
    r = client.post("/api/ai/chat", headers=citizen, json={"message": "any tax due?"}).json()
    assert "Pending dues" in r["reply"] or "no pending" in r["reply"]
    hist = client.get("/api/ai/chat/history", headers=citizen).json()["items"]
    assert [m["role"] for m in hist] == ["user", "assistant", "user", "assistant"]
    assert client.post("/api/ai/chat", headers=citizen, json={"message": ""}).status_code == 422


def test_chat_claude_mode_is_scoped_to_the_citizen(ai_client, fake_ai):
    fake_ai.reply = "तुमचे रेशन कार्ड सक्रिय आहे."
    h = login(ai_client, ("ramesh@example.com", "Citizen@1234"))
    r = ai_client.post("/api/ai/chat", headers=h, json={"message": "माझे रेशन?", "language": "mr"}).json()
    assert r["source"] == "claude" and r["reply"].startswith("तुमचे")
    call = fake_ai.calls[0]
    assert "Marathi" in call["system"] and "MH-RC-1001" in call["system"] and call["model"] == "claude-sonnet-5-5"
    for stranger in ("Sunita", "Vijay", "MH-RC-1002", "MH-RC-1003", "password"):
        assert stranger not in call["system"]


def test_unknown_route_and_bad_json(client, citizen):
    assert client.get("/api/nope").status_code == 404
    r = client.post("/api/ai/chat", headers=citizen, content="not json", )
    assert r.status_code == 400
