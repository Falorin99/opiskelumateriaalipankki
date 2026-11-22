"""Study material SQL queries. All user values are passed as SQL parameters."""

import db

MATERIAL_JOIN = """
    SELECT materials.id, materials.user_id, materials.title,
           materials.description, materials.url, materials.created_at,
           users.username, subjects.name AS subject_name,
           material_types.name AS type_name,
           materials.subject_id, materials.type_id
    FROM materials
    JOIN users ON materials.user_id = users.id
    JOIN subjects ON materials.subject_id = subjects.id
    JOIN material_types ON materials.type_id = material_types.id
"""


def get_materials(search_term=""):
    """Show the newest materials, optionally searching titles and descriptions."""
    if search_term:
        # Treat % and _ as literal characters instead of LIKE wildcards.
        escaped = (search_term.replace("\\", "\\\\")
                   .replace("%", "\\%")
                   .replace("_", "\\_"))
        term = "%" + escaped + "%"
        return db.query(MATERIAL_JOIN + """
            WHERE (materials.title LIKE ? ESCAPE '\\'
                   OR materials.description LIKE ? ESCAPE '\\')
            ORDER BY materials.id DESC
        """, [term, term])
    return db.query(MATERIAL_JOIN + " ORDER BY materials.id DESC")


def get_material(material_id):
    result = db.query(MATERIAL_JOIN + " WHERE materials.id = ?", [material_id])
    return result[0] if result else None


def get_subjects():
    return db.query("SELECT id, name FROM subjects ORDER BY name")


def get_types():
    return db.query("SELECT id, name FROM material_types ORDER BY name")


def subject_exists(subject_id):
    return bool(db.query("SELECT id FROM subjects WHERE id = ?", [subject_id]))


def type_exists(type_id):
    return bool(db.query("SELECT id FROM material_types WHERE id = ?", [type_id]))


def add_material(title, description, url, subject_id, type_id, user_id):
    return db.execute("""
        INSERT INTO materials
        (title, description, url, subject_id, type_id, user_id)
        VALUES (?, ?, ?, ?, ?, ?)
    """, [title, description, url, subject_id, type_id, user_id])


def update_material(material_id, user_id, title, description, url, subject_id, type_id):
    """The user_id check prevents another user from updating the material."""
    db.execute("""
        UPDATE materials
        SET title = ?, description = ?, url = ?, subject_id = ?, type_id = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?
    """, [title, description, url, subject_id, type_id, material_id, user_id])


def delete_material(material_id, user_id):
    """The user_id check prevents another user from deleting the material."""
    db.execute("DELETE FROM materials WHERE id = ? AND user_id = ?",
               [material_id, user_id])
