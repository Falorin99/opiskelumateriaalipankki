"""User queries and password hashing."""
from werkzeug.security import check_password_hash, generate_password_hash

import db


def get_user(user_id):
    result = db.query("SELECT id, username FROM users WHERE id = ?", [user_id])
    return result[0] if result else None


def create_user(username, password):
    password_hash = generate_password_hash(password)
    return db.execute(
        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
        [username, password_hash],
    )


def check_login(username, password):
    result = db.query(
        "SELECT id, password_hash FROM users WHERE username = ? COLLATE NOCASE",
        [username],
    )
    if result and check_password_hash(result[0]["password_hash"], password):
        return result[0]["id"]
    return None
