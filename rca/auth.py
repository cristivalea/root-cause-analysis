import sqlite3
from contextlib import closing
from typing import Any

from pwdlib import PasswordHash

from rca.config import DB_PATH

ROLES = {"problem_manager", "technical_expert"}
password_hash = PasswordHash.recommended()

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('problem_manager', 'technical_expert')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
)
"""


def _connect(db_path=DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute(SCHEMA)
    connection.commit()
    return connection


def get_user(username: str, db_path=DB_PATH) -> dict[str, Any] | None:
    with closing(_connect(db_path)) as connection:
        row = connection.execute(
            """
            SELECT username, password_hash, role, active
            FROM users
            WHERE username = ?
            """,
            (username.strip(),),
        ).fetchone()

    return dict(row) if row else None


def create_user(username: str, password: str, role: str, db_path=DB_PATH) -> None:
    username = username.strip()

    if not username:
        raise ValueError("Numele de utilizator nu poate fi gol.")
    if len(password) < 12:
        raise ValueError("Parola trebuie să aibă cel puțin 12 caractere.")
    if role not in ROLES:
        raise ValueError(f"Rol invalid: {role}")

    hashed_password = password_hash.hash(password)

    with closing(_connect(db_path)) as connection:
        connection.execute(
            """
            INSERT INTO users (username, password_hash, role, active)
            VALUES (?, ?, ?, 1)
            """,
            (username, hashed_password, role),
        )
        connection.commit()


def verify_password(password: str, stored_hash: str) -> bool:
    return password_hash.verify(password, stored_hash)