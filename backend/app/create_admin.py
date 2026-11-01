"""Create an admin account:  python -m app.create_admin "Name" email@example.com   (prompts for the password)"""
from __future__ import annotations

import getpass
import sys

from . import db as dbm
from .config import load_settings
from .schemas import RegisterIn
from .security import hash_password


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    name, email = argv[1], argv[2]
    password = getpass.getpass("Password (8+ chars, letters and numbers): ")
    try:
        RegisterIn(name=name, email=email, mobile="9000000000", age=30, password=password)
    except Exception as exc:  # pydantic ValidationError
        print("Invalid input:", exc)
        return 1
    path = load_settings().database_path
    dbm.init_schema(path)
    conn = dbm.connect(path)
    try:
        if dbm.row(conn, "SELECT 1 FROM users WHERE email = ?", (email.lower(),)):
            print("A user with that email already exists.")
            return 1
        dbm.execute(conn, "INSERT INTO users (name, email, mobile, age, role, password_hash) VALUES (?, ?, '', 30, 'admin', ?)", (name, email.lower(), hash_password(password)))
        conn.commit()
    finally:
        conn.close()
    print("Admin created:", email)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
