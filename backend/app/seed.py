"""Demo data so the product looks alive on first run. Disabled with SEED_DEMO_DATA=false."""
from __future__ import annotations

import json
from datetime import date, timedelta

from . import ai as ai_mod
from . import db as dbm
from .security import hash_password

DEMO_ADMIN = ("admin@gramsathi.in", "Admin@1234")
DEMO_CITIZEN = ("ramesh@example.com", "Citizen@1234")


def seed(path: str) -> bool:
    conn = dbm.connect(path)
    try:
        if dbm.scalar(conn, "SELECT COUNT(*) FROM users"):
            return False
        today = date.today()
        iso = lambda d: d.isoformat()  # noqa: E731

        def user(name, email, pw, mobile, age, role, village="Nashik Rural", address="Main Road, Nashik") -> int:
            return dbm.execute(conn, "INSERT INTO users (name,email,mobile,age,role,village,address,password_hash) VALUES (?,?,?,?,?,?,?,?)",
                               (name, email, mobile, age, role, village, address, hash_password(pw)))

        admin = user("Gram Sevak Patil", DEMO_ADMIN[0], DEMO_ADMIN[1], "9800000001", 41, "admin")
        ramesh = user("Ramesh Jadhav", DEMO_CITIZEN[0], DEMO_CITIZEN[1], "9800000002", 38, "citizen")
        sunita = user("Sunita Pawar", "sunita@example.com", "Citizen@1234", "9800000003", 34, "citizen")
        vijay = user("Vijay Shinde", "vijay@example.com", "Citizen@1234", "9800000004", 52, "citizen")
        meena = user("Meena Kale", "meena@example.com", "Citizen@1234", "9800000005", 29, "citizen")

        for uid, no, typ, end, pt in [(ramesh, "MH-RC-1001", "BPL", today + timedelta(days=200), "Shop No. 4, Main Road"),
                                      (sunita, "MH-RC-1002", "APL", today + timedelta(days=18), "Shop No. 2, Market Yard"),
                                      (vijay, "MH-RC-1003", "AAY", today + timedelta(days=400), "Shop No. 4, Main Road")]:
            cid = dbm.execute(conn, "INSERT INTO ration_cards (user_id,card_no,card_type,validity_start,validity_end,distribution_point,last_distribution) VALUES (?,?,?,?,?,?,?)",
                              (uid, no, typ, iso(today - timedelta(days=300)), iso(end), pt, iso(today - timedelta(days=12))))
            for name, q in (("Rice", 10), ("Wheat", 15), ("Sugar", 1), ("Dal", 2)):
                dbm.execute(conn, "INSERT INTO ration_items (card_id,name,quantity,unit) VALUES (?,?,?,'kg')", (cid, name, q))

        c1 = dbm.execute(conn, "INSERT INTO anganwadi_centers (name,address,phone,latitude,longitude,services,open_time,close_time) VALUES (?,?,?,?,?,?,?,?)",
                         ("Anganwadi Center 1 - Panchavati", "Near Gram Panchayat Office", "02532000001", 20.0059, 73.7897,
                          json.dumps(["Nutrition Support", "Pre-school", "Health Checkup", "Immunization"]), "09:00", "16:00"))
        c2 = dbm.execute(conn, "INSERT INTO anganwadi_centers (name,address,phone,latitude,longitude,services,open_time,close_time) VALUES (?,?,?,?,?,?,?,?)",
                         ("Anganwadi Center 2 - Gangapur", "Gangapur Road", "02532000002", 20.0125, 73.7551,
                          json.dumps(["Nutrition Support", "Pre-school", "ICDS Schemes"]), "09:30", "15:30"))
        dbm.execute(conn, "INSERT INTO anganwadi_beneficiaries (user_id,center_id,child_name,age_group,enrollment_date,last_visit) VALUES (?,?,?,?,?,?)", (ramesh, c1, "Aarav Jadhav", "0-6", iso(today - timedelta(days=200)), iso(today - timedelta(days=3))))
        dbm.execute(conn, "INSERT INTO anganwadi_beneficiaries (user_id,center_id,child_name,age_group,enrollment_date,last_visit) VALUES (?,?,?,?,?,?)", (sunita, c1, "Diya Pawar", "0-6", iso(today - timedelta(days=90)), iso(today - timedelta(days=5))))
        dbm.execute(conn, "INSERT INTO anganwadi_beneficiaries (user_id,center_id,child_name,age_group,enrollment_date,last_visit) VALUES (?,?,?,?,?,?)", (vijay, c2, "Kabir Shinde", "6-14", iso(today - timedelta(days=400)), iso(today - timedelta(days=40))))

        for uid, no in ((ramesh, "WC-2001"), (sunita, "WC-2002"), (vijay, "WC-2003")):
            wid = dbm.execute(conn, "INSERT INTO water_connections (user_id,connection_no) VALUES (?,?)", (uid, no))
            for i in range(1, 4):
                due = today - timedelta(days=30 * i - 10)
                dbm.execute(conn, "INSERT INTO water_bills (connection_id,period,amount,due_date,paid,paid_on) VALUES (?,?,?,?,?,?)",
                            (wid, iso(due)[:7], 180 + 15 * i, iso(due), 1 if (i > 1 or uid == ramesh) else 0, iso(due) if (i > 1 or uid == ramesh) else None))
        for uid, no, val, rate, due, paid in ((ramesh, "PT-3001", 850000, 0.4, today + timedelta(days=45), 0),
                                              (vijay, "PT-3002", 1450000, 0.45, today - timedelta(days=20), 0),
                                              (sunita, "PT-3003", 620000, 0.35, today + timedelta(days=60), 1)):
            dbm.execute(conn, "INSERT INTO properties (user_id,property_no,address,area_sqft,value,tax_rate,annual_tax,due_date,paid,last_paid) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (uid, no, "Plot, Nashik Rural", 1200, val, rate, round(val * rate / 100, 2), iso(due), paid, iso(today) if paid else None))

        for title, desc, cat, pri in (
            ("Free health camp this Sunday", "A free health checkup and vaccination camp will be held at the Gram Panchayat hall from 9 AM to 1 PM.", "health", 3),
            ("Last date for property tax", "Please pay your annual property tax before the due date to avoid a penalty.", "deadline", 4),
            ("PM Awas Yojana applications open", "Eligible families can apply for housing assistance at the panchayat office with Aadhaar and income proof.", "scheme", 3),
        ):
            dbm.execute(conn, "INSERT INTO news (title,description,category,priority,created_by) VALUES (?,?,?,?,?)", (title, desc, cat, pri, admin))

        def doc(uid, typ, status, **data):
            base = {"date_of_birth": "2019-05-14", "address": "Main Road, Nashik Rural", "mother_name": "", "place_of_birth": "", "purpose": "", "school_name": ""}
            base.update(data)
            applicant = dbm.row(conn, "SELECT name FROM users WHERE id = ?", (uid,))
            review = ai_mod.rule_based_review(typ, base, applicant, 0)
            dbm.execute(conn, "INSERT INTO documents (user_id,doc_type,status,data,ai_review,reviewed_by,reviewed_at) VALUES (?,?,?,?,?,?,?)",
                        (uid, typ, status, json.dumps(base), json.dumps(review), admin if status != "pending" else None, iso(today) if status != "pending" else None))

        doc(ramesh, "birth_certificate", "approved", full_name="Aarav Jadhav", father_name="Ramesh Jadhav", mother_name="Priya Jadhav", place_of_birth="Civil Hospital, Nashik")
        doc(sunita, "bonafide_certificate", "pending", full_name="Diya Pawar", father_name="Sunita Pawar", school_name="ZP School Nashik", purpose="Scholarship")
        doc(meena, "birth_certificate", "pending", full_name="Rohan Kale", father_name="Meena Kale", date_of_birth="2021-02-02")
        # Rozgar sample jobs: two published opportunities and one flagged moderation item.
        jobs = [
            (ramesh, 'Junior Data Entry Operator', 'Nashik Agro Services', 'Maintain Excel records, verify farmer applications and update daily reports. Basic computer skills and attention to detail required.', ['Excel', 'Data Entry', 'Communication'], 'Nashik', 'Full-time', 12000, 16000, 'published', 0, []),
            (sunita, 'Python Developer Intern', 'RuralTech Labs', 'Assist the engineering team with Python scripts, REST API testing and database updates. Suitable for fresh graduates.', ['Python', 'SQL', 'REST API'], 'Pune', 'Internship', 8000, 12000, 'published', 0, []),
            (vijay, 'Work from home guaranteed income', 'QuickMoney Jobs', 'Pay registration fee to get job. WhatsApp only. Guaranteed income.', ['Typing'], 'Remote', 'Part-time', 25000, 50000, 'pending', 70, ['registration fee', 'guaranteed income', 'whatsapp only'])
        ]
        for employer, title, company, desc, skills, location, typ, lo, hi, status, score, flags in jobs:
            dbm.execute(conn, 'INSERT INTO rozgar_jobs(employer_id,title,company,description,skills,location,job_type,salary_min,salary_max,status,scam_score,scam_flags) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                         (employer,title,company,desc,json.dumps(skills),location,typ,lo,hi,status,score,json.dumps(flags)))
        conn.commit()
        return True
    finally:
        conn.close()
