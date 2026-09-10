"""Category workflow checks using disposable SQLite data, not production MySQL.

Run from the project root: python -m unittest discover -s tests -v
The adapter translates placeholders, INSERT IGNORE and auto-increment DDL only.
"""

import contextlib
import io
import os
from pathlib import Path
import runpy
import sqlite3
import tempfile
import unittest
from datetime import date
from html.parser import HTMLParser
from unittest.mock import patch

with patch.dict(os.environ, {"SECRET_KEY": "category-tests-only"}):
    import app as tracker


sqlite3.register_converter("DATE", lambda value: date.fromisoformat(value.decode()))


def sqlite_query(query):
    return (query.replace("%s", "?")
            .replace("INSERT IGNORE", "INSERT OR IGNORE")
            .replace("INT AUTO_INCREMENT PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT"))


class Cursor:
    def __init__(self, connection, dictionary=False):
        self.raw = connection.cursor()
        self.dictionary = dictionary

    def execute(self, query, values=()):
        self.raw.execute(sqlite_query(query), values)

    def executemany(self, query, values):
        self.raw.executemany(sqlite_query(query), values)

    def convert(self, row):
        if row is None or not self.dictionary:
            return row
        return dict(zip([column[0] for column in self.raw.description], row))

    def fetchone(self):
        return self.convert(self.raw.fetchone())

    def fetchall(self):
        return [self.convert(row) for row in self.raw.fetchall()]

    def close(self):
        self.raw.close()


class Connection:
    def __init__(self, path):
        self.raw = sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES)
        self.raw.execute("PRAGMA foreign_keys = ON")
        self.raw.create_function("CURDATE", 0, lambda: date.today().isoformat())

    def cursor(self, dictionary=False):
        return Cursor(self.raw, dictionary)

    def commit(self):
        self.raw.commit()

    def close(self):
        self.raw.close()


class SelectOptions(HTMLParser):
    def __init__(self, source, select_id):
        super().__init__()
        self.select_id = select_id
        self.inside = False
        self.options = {}
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "select":
            self.inside = attrs.get("id") == self.select_id
        elif tag == "option" and self.inside:
            self.options[attrs.get("value")] = "selected" in attrs

    def handle_endtag(self, tag):
        if tag == "select":
            self.inside = False


class CategoryRemovalTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="tracker-categories-")
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "test.sqlite"
        self.initialize()
        with sqlite3.connect(self.path) as connection:
            connection.executemany(
                "INSERT INTO users (id, name, email, password) VALUES (?, ?, ?, ?)",
                [(1, "First", "first@example.invalid", "unused"),
                 (2, "Second", "second@example.invalid", "unused")],
            )
        connection_patch = patch.object(
            tracker, "get_database_connection", lambda: Connection(self.path)
        )
        connection_patch.start()
        self.addCleanup(connection_patch.stop)
        config_patch = patch.dict(tracker.app.config, TESTING=True, SECRET_KEY="category-tests-only")
        config_patch.start()
        self.addCleanup(config_patch.stop)
        self.client = self.signed_in_client(1)
        self.other_client = self.signed_in_client(2)
        self.dsa_id = self.rows("SELECT id FROM categories WHERE name = 'DSA'")[0][0]

    def initialize(self):
        with patch("mysql.connector.connect", side_effect=lambda **kwargs: Connection(self.path)):
            with contextlib.redirect_stdout(io.StringIO()):
                runpy.run_path(str(Path(tracker.__file__).with_name("init_db.py")))

    def signed_in_client(self, user_id):
        client = tracker.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = user_id
            session["user_name"] = "Test user"
        return client

    def rows(self, query, values=()):
        with sqlite3.connect(self.path) as connection:
            return connection.execute(query, values).fetchall()

    def activity(self, user_id=1, category="DSA"):
        with sqlite3.connect(self.path) as connection:
            cursor = connection.execute(
                """INSERT INTO study_records (user_id, category, subject, minutes, study_date)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, category, f"Practice by {user_id}", 30, date.today().isoformat()),
            )
            return cursor.lastrowid

    def remove(self, client=None, category_id=None):
        return (client or self.client).post(
            f"/categories/delete/{category_id or self.dsa_id}", follow_redirects=True
        )

    def options(self, client=None, path="/dashboard", select_id="category"):
        response = (client or self.client).get(path)
        self.assertEqual(response.status_code, 200)
        return SelectOptions(response.get_data(as_text=True), select_id).options

    def test_used_default_removal_preserves_all_history_and_other_account_choices(self):
        self.activity(1)
        self.activity(2)
        before = self.rows("SELECT * FROM study_records ORDER BY id")
        response = self.remove()
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(f'/categories/delete/{self.dsa_id}"', response.get_data(as_text=True))
        self.assertIn(b"Category removed from your list", response.data)
        self.assertNotIn("DSA", self.options())
        self.assertIn("DSA", self.options(self.other_client))
        self.assertEqual(before, self.rows("SELECT * FROM study_records ORDER BY id"))

    def test_unused_custom_category_can_be_removed_without_affecting_another_user(self):
        self.client.post("/categories", data={"name": "Reading"})
        category_id = self.rows("SELECT id FROM categories WHERE name = 'Reading'")[0][0]
        self.remove(category_id=category_id)
        self.assertNotIn("Reading", self.options())
        self.assertIn("Reading", self.options(self.other_client))

    def test_removed_defaults_stay_removed_after_setup_and_new_login(self):
        self.remove()
        self.client.post("/logout")
        self.initialize()
        self.client = self.signed_in_client(1)
        self.assertNotIn("DSA", self.options())
        self.assertIn("DSA", self.options(self.other_client))

    def test_upgrade_keeps_existing_data_and_allows_new_activities(self):
        self.activity(1)
        self.activity(2)
        before = self.rows("SELECT * FROM study_records ORDER BY id")
        with sqlite3.connect(self.path) as connection:
            connection.execute("DROP TABLE user_hidden_categories")
        self.initialize()
        self.assertEqual(before, self.rows("SELECT * FROM study_records ORDER BY id"))
        self.assertEqual(self.rows("SELECT COUNT(*) FROM users"), [(2,)])
        response = self.client.post("/dashboard", data={
            "category": "DSA", "subject": "After upgrade", "minutes": "20",
            "study_date": date.today().isoformat(),
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.rows(
            "SELECT user_id, category, minutes FROM study_records WHERE subject = 'After upgrade'"
        ), [(1, "DSA", 20)])

    def test_history_filter_and_export_still_include_removed_categories(self):
        self.activity(1)
        self.activity(2)
        self.remove()
        filters = self.options(path="/dashboard?filter_category=DSA", select_id="filter_category")
        self.assertTrue(filters["DSA"])
        response = self.client.get("/export?filter_category=DSA")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"DSA,Practice by 1,30", response.data)
        self.assertNotIn(b"Practice by 2", response.data)

    def test_existing_activity_can_keep_its_removed_category_when_edited(self):
        record_id = self.activity()
        self.remove()
        options = self.options(path=f"/edit/{record_id}")
        self.assertTrue(options["DSA"])
        response = self.client.post(f"/edit/{record_id}", data={
            "category": "DSA", "subject": "Updated practice", "minutes": "45",
            "study_date": date.today().isoformat(),
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self.rows("SELECT category, subject, minutes FROM study_records WHERE id = ?", (record_id,)),
            [("DSA", "Updated practice", 45)],
        )

    def test_adding_same_name_restores_only_current_users_choice(self):
        self.remove()
        self.remove(self.other_client)
        response = self.client.post("/categories", data={"name": "DSA"}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("DSA", self.options())
        self.assertNotIn("DSA", self.options(self.other_client))
        self.assertEqual(self.rows("SELECT COUNT(*) FROM categories WHERE name = 'DSA'"), [(1,)])

    def test_all_categories_can_be_removed_then_a_new_one_added(self):
        self.activity()
        for (category_id,) in self.rows("SELECT id FROM categories"):
            self.remove(category_id=category_id)
        self.initialize()
        self.assertEqual(set(self.options()), {""})
        self.assertIn(b"No categories available", self.client.get("/categories").data)
        self.assertIn("DSA", self.options(select_id="filter_category"))
        self.client.post("/categories", data={"name": "Machine Learning"})
        self.assertEqual(set(self.options()), {"", "Machine Learning"})
        self.assertEqual(self.rows("SELECT COUNT(*) FROM study_records"), [(1,)])

    def test_stale_activity_form_does_not_reuse_removed_choice(self):
        self.remove()
        response = self.client.post("/dashboard", data={
            "category": "DSA", "subject": "Stale form", "minutes": "30",
            "study_date": date.today().isoformat(),
        })
        self.assertIn(b"Please enter valid activity details", response.data)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM study_records"), [(0,)])

    def test_repeated_or_missing_removals_are_safe_and_require_authenticated_post(self):
        self.assertEqual(self.remove().status_code, 200)
        self.assertEqual(self.remove().status_code, 200)
        self.assertNotIn("DSA", self.options())
        self.assertEqual(self.remove(category_id=9999).status_code, 200)
        path = f"/categories/delete/{self.dsa_id}"
        self.assertEqual(self.client.get(path).status_code, 405)
        self.assertEqual(tracker.app.test_client().post(path).location, "/login")


if __name__ == "__main__":
    unittest.main()
