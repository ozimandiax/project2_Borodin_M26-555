"""Check exact query results and observable cache behaviour."""

import contextlib
import io
import os
import tempfile
import unittest
from unittest.mock import patch

from primitive_db import core, engine
from primitive_db.utils import save_table_data


class QueryTests(unittest.TestCase):
    """Exercise queries against a separate database for every test."""

    def setUp(self):
        """Create a disposable working directory with two distinct records."""
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        original_directory = os.getcwd()
        os.chdir(self.directory.name)
        self.addCleanup(os.chdir, original_directory)
        engine.reset_select_cache()
        self.addCleanup(engine.reset_select_cache)
        self.command("create_table users name:str age:int active:bool")
        self.command('insert into users values ("Sergei", 28, true)')
        self.command('insert into users values ("Anna, Maria", 25, false)')
        self.rows = [
            {"ID": 1, "name": "Sergei", "age": 28, "active": True},
            {"ID": 2, "name": "Anna, Maria", "age": 25, "active": False},
        ]
        self.schema = {"ID": "int", "name": "str", "age": "int", "active": "bool"}

    def command(self, text):
        """Run one command and fail on an unexpected application error."""
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = engine.process_input(text)
        self.assertIs(result, True, output.getvalue())
        self.assertNotIn("Ошибка", output.getvalue())
        return output.getvalue()

    def query_rows(self, text):
        """Read every displayed cell, including the header, from a query."""
        return [
            [cell.strip() for cell in line.strip().strip("|").split("|")]
            for line in self.command(text).splitlines()
            if line.lstrip().startswith("|")
        ]

    def test_select_without_condition_returns_every_record(self):
        """An unfiltered query returns both complete records in order."""
        self.assertEqual(
            self.query_rows("select from users"),
            [
                ["ID", "name", "age", "active"],
                ["1", "Sergei", "28", "True"],
                ["2", "Anna, Maria", "25", "False"],
            ],
        )

    def test_filter_excludes_nonmatching_records(self):
        """The matching row is present and the other row is absent."""
        self.assertEqual(
            self.query_rows("select from users where ID = 1"),
            [["ID", "name", "age", "active"], ["1", "Sergei", "28", "True"]],
        )
        self.assertEqual(
            self.query_rows('select from users where name = "Anna, Maria"'),
            [["ID", "name", "age", "active"], ["2", "Anna, Maria", "25", "False"]],
        )

    def test_empty_query_displays_only_column_headers(self):
        """An unmatched filter produces an empty table with its schema."""
        self.assertEqual(
            self.query_rows("select from users where ID = 999"),
            [["ID", "name", "age", "active"]],
        )

    def test_select_distinguishes_boolean_integer_and_string_values(self):
        """Python's equality of True and 1 must not merge database types."""
        records = [
            {"ID": 1, "value": 1},
            {"ID": 2, "value": True},
            {"ID": 3, "value": "1"},
        ]
        with contextlib.redirect_stdout(io.StringIO()):
            for value, identifier in [(1, 1), (True, 2), ("1", 3)]:
                with self.subTest(value=value):
                    self.assertEqual(
                        core.select(records, {"value": value}),
                        [records[identifier - 1]],
                    )

    def test_identical_query_filters_only_once(self):
        """A repeated query must use the cached result, not just equal output."""
        with patch("primitive_db.engine.select", wraps=core.select) as select:
            first = self.query_rows("select from users where ID = 1")
            second = self.query_rows("select from users where ID = 1")
        self.assertEqual(first, second)
        self.assertEqual(select.call_count, 1)

    def test_empty_query_result_is_cached(self):
        """An empty list is a valid cached result."""
        with patch("primitive_db.engine.select", wraps=core.select) as select:
            self.query_rows("select from users where ID = 999")
            self.query_rows("select from users where ID = 999")
        self.assertEqual(select.call_count, 1)

    def test_cached_rows_are_isolated_from_the_caller(self):
        """Changing a returned record or list cannot change a later result."""
        with contextlib.redirect_stdout(io.StringIO()):
            first = engine.cached_select("users", self.schema, self.rows)
            first[0]["name"] = "Changed by caller"
            first.pop()
            second = engine.cached_select("users", self.schema, self.rows)
        self.assertEqual(second, self.rows)

    def test_cache_separates_conditions(self):
        """Queries for different IDs must not share their selected records."""
        with patch("primitive_db.engine.select", wraps=core.select) as select:
            first = self.query_rows("select from users where ID = 1")
            second = self.query_rows("select from users where ID = 2")
            self.query_rows("select from users where ID = 1")
        self.assertEqual(first[-1][0], "1")
        self.assertEqual(second[-1][0], "2")
        self.assertEqual(select.call_count, 2)

    def test_update_refreshes_repeated_query(self):
        """A cached query shows the persisted update and then hits the cache."""
        self.query_rows("select from users where ID = 1")
        self.command('update users set name = "Updated" where ID = 1')
        with patch("primitive_db.engine.select", wraps=core.select) as select:
            first = self.query_rows("select from users where ID = 1")
            second = self.query_rows("select from users where ID = 1")
        self.assertEqual(first[-1], ["1", "Updated", "28", "True"])
        self.assertEqual(second, first)
        self.assertEqual(select.call_count, 1)

    def test_insert_and_delete_refresh_cached_results(self):
        """Insert and confirmed deletion change an already cached query."""
        self.query_rows("select from users")
        self.command('insert into users values ("New", 30, true)')
        self.assertEqual(self.query_rows("select from users")[-1][0], "3")
        with patch("builtins.input", return_value="y"):
            self.command("delete from users where ID = 1")
        self.assertEqual(
            [row[0] for row in self.query_rows("select from users")[1:]],
            ["2", "3"],
        )

    def test_external_file_change_refreshes_cached_query(self):
        """A change outside the command loop cannot leave the query stale."""
        self.query_rows("select from users where ID = 1")
        changed = [dict(row) for row in self.rows]
        changed[0]["name"] = "External change"
        save_table_data("users", changed)
        with patch("primitive_db.engine.select", wraps=core.select) as select:
            first = self.query_rows("select from users where ID = 1")
            second = self.query_rows("select from users where ID = 1")
        self.assertEqual(first[-1], ["1", "External change", "28", "True"])
        self.assertEqual(second, first)
        self.assertEqual(select.call_count, 1)


if __name__ == "__main__":
    unittest.main()
