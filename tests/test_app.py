"""Functional tests for the second StudyHub milestone (unittest + Flask test client)."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

import config
from app import app


class StudyHubTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.old_db_path = config.database_path
        config.database_path = Path(self.folder.name) / "test.db"
        root = Path(__file__).resolve().parents[1]
        with sqlite3.connect(config.database_path) as connection:
            connection.executescript((root / "schema.sql").read_text(encoding="utf-8"))
            connection.executescript((root / "init.sql").read_text(encoding="utf-8"))
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def tearDown(self):
        config.database_path = self.old_db_path
        self.folder.cleanup()

    def csrf(self):
        with self.client.session_transaction() as user_session:
            return user_session["csrf_token"]

    def register(self, username="student1"):
        self.assertEqual(self.client.get("/register").status_code, 200)
        return self.client.post("/register", data={
            "username": username,
            "password": "safe-password-123",
            "csrf_token": self.csrf(),
        }, follow_redirects=True)

    def logout(self):
        return self.client.post("/logout", data={
            "csrf_token": self.csrf()
        }, follow_redirects=True)

    def add_material(self, title="Python basics"):
        self.assertEqual(self.client.get("/materials/new").status_code, 200)
        return self.client.post("/materials/create", data={
            "title": title,
            "description": "Helpful beginner lessons.",
            "url": "https://example.org/python",
            "subject_id": "1",
            "type_id": "1",
            "csrf_token": self.csrf(),
        }, follow_redirects=True)

    def test_front_page_and_static_css(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/static/style.css").status_code, 200)
        self.assertIn(b'Hae materiaaleja', self.client.get("/").data)

    def test_register_login_logout(self):
        response = self.register()
        self.assertIn(b"student1", response.data)
        self.assertEqual(self.logout().status_code, 200)
        self.assertEqual(self.client.get("/login").status_code, 200)
        response = self.client.post("/login", data={
            "username": "student1", "password": "safe-password-123",
            "csrf_token": self.csrf(),
        }, follow_redirects=True)
        self.assertIn(b"student1", response.data)

    def test_create_edit_search_delete_material(self):
        self.register()
        response = self.add_material()
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Python basics", response.data)
        self.assertIn(b"Python basics", self.client.get("/").data)
        self.assertEqual(self.client.get("/materials/1/edit").status_code, 200)
        response = self.client.post("/materials/1/update", data={
            "title": "Data structures in Python",
            "description": "A detailed introduction to useful data structures.",
            "url": "https://example.org/data-structures",
            "subject_id": "2", "type_id": "3",
            "csrf_token": self.csrf(),
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Data structures in Python", response.data)
        self.assertNotIn(b"Python basics", self.client.get("/materials/1").data)
        self.assertIn(b"Data structures in Python", self.client.get("/?q=structures").data)
        self.assertIn(b"Data structures in Python", self.client.get("/?q=DETAILED").data)
        self.assertNotIn(b"Data structures in Python", self.client.get("/?q=Java").data)
        self.assertEqual(self.client.get("/materials/1/delete").status_code, 200)
        response = self.client.post("/materials/1/delete", data={
            "csrf_token": self.csrf()
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/materials/1").status_code, 404)

    def test_non_owner_cannot_edit_or_delete(self):
        self.register()
        self.add_material()
        self.logout()
        self.register("student2")
        self.assertIn(b"Python basics", self.client.get("/").data)
        self.assertEqual(self.client.get("/materials/1/edit").status_code, 403)
        self.assertEqual(self.client.get("/materials/1/delete").status_code, 403)
        self.assertEqual(self.client.post("/materials/1/update", data={
            "title": "Stolen changes", "description": "A very long description",
            "url": "https://example.org", "subject_id": "1", "type_id": "1",
            "csrf_token": self.csrf(),
        }).status_code, 403)
        self.assertEqual(self.client.post("/materials/1/delete", data={
            "csrf_token": self.csrf(),
        }).status_code, 403)
        self.assertIn(b"Python basics", self.client.get("/materials/1").data)

    def test_csrf_and_login_checks(self):
        self.assertEqual(self.client.get("/materials/new").status_code, 403)
        self.register()
        self.add_material()
        self.assertEqual(self.client.post("/materials/1/delete", data={
            "csrf_token": "wrong-token"
        }).status_code, 403)
        self.assertEqual(self.client.post("/materials/1/update", data={
            "csrf_token": "wrong-token"
        }).status_code, 403)
        self.assertEqual(self.client.get("/materials/1").status_code, 200)

    def test_reject_invalid_material_data(self):
        self.register()
        response = self.client.post("/materials/create", data={
            "title": "ok", "description": "short", "url": "javascript:alert(1)",
            "subject_id": "9999", "type_id": "1", "csrf_token": self.csrf()
        })
        self.assertEqual(response.status_code, 400)
        with sqlite3.connect(config.database_path) as connection:
            count = connection.execute("SELECT COUNT(*) FROM materials").fetchone()[0]
        self.assertEqual(count, 0)

    def test_search_treats_sql_wildcards_as_text(self):
        self.register()
        self.add_material("100% Python basics")
        self.add_material("100 students")
        self.assertIn(b"100% Python basics", self.client.get("/?q=%25").data)
        self.assertNotIn(b"100 students", self.client.get("/?q=%25").data)
        self.assertEqual(self.client.get("/?q=" + "a" * 101).status_code, 400)


if __name__ == "__main__":
    unittest.main()
