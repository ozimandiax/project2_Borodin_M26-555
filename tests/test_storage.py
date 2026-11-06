"""Protect existing records and metadata when filesystem operations fail."""

import contextlib
import io
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from primitive_db import engine, utils
from primitive_db.constants import ACTION_CANCELLED, DB_ERROR, META_FILE


class FailingWriter:
    """Write part of the payload before simulating an exhausted disk."""

    def __init__(self, stream):
        self.stream = stream

    def __enter__(self):
        self.stream.__enter__()
        return self

    def __exit__(self, *args):
        return self.stream.__exit__(*args)

    def __getattr__(self, name):
        return getattr(self.stream, name)

    def write(self, payload):
        """Ensure the failure occurs after actual bytes reach the temp file."""
        self.stream.write(payload[:7])
        self.stream.flush()
        raise OSError("simulated disk-full during write")


class StorageTests(unittest.TestCase):
    """Use disposable databases; never read or change a user's database."""

    def setUp(self):
        self.original_directory = Path.cwd()
        self.directory = tempfile.TemporaryDirectory(prefix="primitive-db-test-")
        os.chdir(self.directory.name)
        engine.reset_select_cache()
        self.metadata = {"users": ["ID:int", "name:str"]}
        self.records = [{"ID": 1, "name": "Сергей"}]
        utils.save_metadata(META_FILE, self.metadata)
        utils.save_table_data("users", self.records)

    def tearDown(self):
        os.chdir(self.original_directory)
        self.directory.cleanup()

    def snapshot(self):
        """Include temporary files so failure cleanup is also observable."""
        return {
            str(path): path.read_bytes()
            for path in Path(".").rglob("*")
            if path.is_file()
        }

    def drop_table(self, answer="y"):
        """Exercise the real command handler and capture the user message."""
        output = io.StringIO()
        with patch("builtins.input", return_value=answer):
            with contextlib.redirect_stdout(output):
                result = engine.execute_table_command(
                    {"command": "drop_table", "table_name": "users"},
                    self.metadata,
                )
        return result, output.getvalue()

    def test_successful_writes_replace_json_without_temporary_files(self):
        """The complete new value must be visible after the save returns."""
        updated_records = [*self.records, {"ID": 2, "name": "Анна"}]
        updated_metadata = {**self.metadata, "orders": ["ID:int"]}
        utils.save_table_data("users", updated_records)
        utils.save_metadata(META_FILE, updated_metadata)

        self.assertEqual(utils.load_table_data("users"), updated_records)
        self.assertEqual(utils.load_metadata(META_FILE), updated_metadata)
        self.assertEqual(
            set(self.snapshot()), {META_FILE, str(Path("data/users.json"))}
        )

    def test_partial_write_keeps_existing_records_and_metadata(self):
        """A disk-full error must not truncate either existing JSON file."""
        original_fdopen = os.fdopen

        def fail_write(*args, **kwargs):
            return FailingWriter(original_fdopen(*args, **kwargs))

        saves = (
            lambda: utils.save_table_data("users", [{"ID": 2, "name": "Новая"}]),
            lambda: utils.save_metadata(META_FILE, {"orders": ["ID:int"]}),
        )
        for save in saves:
            with self.subTest(save=save):
                before = self.snapshot()
                with patch.object(
                    utils.os,
                    "fdopen",
                    side_effect=fail_write,
                ):
                    with self.assertRaises(OSError):
                        save()
                self.assertEqual(self.snapshot(), before)

    def test_replace_failure_keeps_existing_records_and_metadata(self):
        """Failure at commit must leave the old complete JSON and no temp file."""
        saves = (
            lambda: utils.save_table_data("users", [{"ID": 2, "name": "Новая"}]),
            lambda: utils.save_metadata(META_FILE, {}),
        )
        for save in saves:
            with self.subTest(save=save):
                before = self.snapshot()
                with patch.object(
                    utils.os, "replace", side_effect=OSError("replace failed")
                ):
                    with self.assertRaises(OSError):
                        save()
                self.assertEqual(self.snapshot(), before)

    def test_fsync_failure_keeps_existing_records(self):
        """An error while flushing to disk must happen before committing."""
        before = self.snapshot()
        with patch.object(utils.os, "fsync", side_effect=OSError("flush failed")):
            with self.assertRaises(OSError):
                utils.save_table_data("users", [{"ID": 2, "name": "Новая"}])
        self.assertEqual(self.snapshot(), before)

    def test_serialization_failure_keeps_existing_records_and_metadata(self):
        """Invalid Python values must not modify existing files."""
        before = self.snapshot()
        with self.assertRaises(TypeError):
            utils.save_table_data("users", [{"ID": 2, "name": object()}])
        with self.assertRaises(TypeError):
            utils.save_metadata(META_FILE, {"bad": object()})
        self.assertEqual(self.snapshot(), before)

    def test_delete_file_failure_preserves_files_and_in_memory_metadata(self):
        """A refused unlink must not remove a table from the database."""
        before = self.snapshot()
        table_path = Path(utils.get_table_path("users"))
        original_remove = os.remove

        def denied_remove(path, *args, **kwargs):
            if Path(path).resolve() == table_path:
                raise PermissionError("simulated access denied")
            return original_remove(path, *args, **kwargs)

        with patch.object(utils.os, "remove", side_effect=denied_remove):
            result, output = self.drop_table()

        self.assertIs(result, DB_ERROR)
        self.assertIn("Ошибка работы с файлом", output)
        self.assertNotIn("успешно удалена", output)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.metadata, utils.load_metadata(META_FILE))

    @unittest.skipUnless(os.name == "nt", "Windows enforces the readonly attribute")
    def test_readonly_file_preserves_table_on_windows(self):
        """Reproduce the review finding using an actual Windows filesystem error."""
        before = self.snapshot()
        table_path = Path(utils.get_table_path("users"))
        table_path.chmod(stat.S_IREAD)
        try:
            result, output = self.drop_table()
            self.assertIs(result, DB_ERROR)
            self.assertIn("Ошибка работы с файлом", output)
            self.assertEqual(self.snapshot(), before)
            self.assertEqual(self.metadata, utils.load_metadata(META_FILE))
        finally:
            table_path.chmod(stat.S_IREAD | stat.S_IWRITE)

    def test_failed_metadata_save_restores_records_and_in_memory_metadata(self):
        """A failed second step must roll back an already removed data file."""
        before = self.snapshot()
        with patch.object(
            utils, "save_metadata", side_effect=OSError("metadata failed")
        ):
            result, output = self.drop_table()

        self.assertIs(result, DB_ERROR)
        self.assertIn("Ошибка работы с файлом", output)
        self.assertNotIn("успешно удалена", output)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.metadata, utils.load_metadata(META_FILE))

    def test_backup_failure_does_not_remove_original_data(self):
        """The original table must survive a failure while preparing the backup."""
        before = self.snapshot()
        original_fdopen = os.fdopen

        def fail_write(*args, **kwargs):
            return FailingWriter(original_fdopen(*args, **kwargs))

        with patch.object(
            utils.os,
            "fdopen",
            side_effect=fail_write,
        ):
            result, output = self.drop_table()

        self.assertIs(result, DB_ERROR)
        self.assertIn("Ошибка работы с файлом", output)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.metadata, utils.load_metadata(META_FILE))

    def test_restore_failure_keeps_recoverable_backup_and_reports_its_path(self):
        """A second error must not discard the last surviving copy of records."""
        before = self.snapshot()
        table_path = Path(utils.get_table_path("users"))
        original_bytes = table_path.read_bytes()
        with patch.object(
            utils, "save_metadata", side_effect=OSError("metadata failed")
        ):
            with patch.object(
                utils.os, "replace", side_effect=PermissionError("restore denied")
            ):
                result, output = self.drop_table()

        self.assertIs(result, DB_ERROR)
        self.assertIn("Резервная копия сохранена", output)
        self.assertFalse(table_path.exists())
        after = self.snapshot()
        self.assertEqual(after[META_FILE], before[META_FILE])
        backups = [path for path, data in after.items() if data == original_bytes]
        self.assertEqual(len(backups), 1)
        self.assertIn(Path(backups[0]).name, output)
        self.assertEqual(self.metadata, utils.load_metadata(META_FILE))

    def test_backup_cleanup_failure_does_not_undo_committed_drop(self):
        """A leftover backup is reported without misreporting a committed deletion."""
        table_path = Path(utils.get_table_path("users"))
        original_bytes = table_path.read_bytes()
        original_remove = os.remove

        def denied_backup_remove(path, *args, **kwargs):
            candidate = Path(path)
            if candidate.is_file() and candidate.resolve() != table_path:
                raise PermissionError("backup cleanup denied")
            return original_remove(path, *args, **kwargs)

        with patch.object(utils.os, "remove", side_effect=denied_backup_remove):
            result, output = self.drop_table()

        self.assertIsNot(result, DB_ERROR)
        self.assertIn("Не удалось удалить временный файл", output)
        self.assertIn('Таблица "users" успешно удалена.', output)
        self.assertEqual(self.metadata, {})
        self.assertEqual(utils.load_metadata(META_FILE), {})
        self.assertFalse(table_path.exists())
        backups = [
            path for path, data in self.snapshot().items() if data == original_bytes
        ]
        self.assertEqual(len(backups), 1)

    def test_successful_drop_removes_table_and_updates_metadata(self):
        """Commit the deletion in memory and on disk without leftover backups."""
        result, output = self.drop_table()
        self.assertIsNot(result, DB_ERROR)
        self.assertIn('Таблица "users" успешно удалена.', output)
        self.assertEqual(self.metadata, {})
        self.assertEqual(utils.load_metadata(META_FILE), {})
        self.assertFalse(Path(utils.get_table_path("users")).exists())
        self.assertEqual(set(self.snapshot()), {META_FILE})

    def test_drop_tolerates_an_already_missing_data_file(self):
        """A missing file should not prevent removing the remaining schema."""
        Path(utils.get_table_path("users")).unlink()
        result, output = self.drop_table()
        self.assertIsNot(result, DB_ERROR)
        self.assertIn("успешно удалена", output)
        self.assertEqual(self.metadata, {})
        self.assertEqual(utils.load_metadata(META_FILE), {})
        self.assertEqual(set(self.snapshot()), {META_FILE})

    def test_cancelled_drop_keeps_files_and_in_memory_metadata(self):
        """Confirmation refusal must not start a storage transaction."""
        before = self.snapshot()
        result, output = self.drop_table(answer="n")
        self.assertIs(result, ACTION_CANCELLED)
        self.assertIn("Операция отменена.", output)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.metadata, utils.load_metadata(META_FILE))

    def test_fdopen_failure_closes_descriptor_and_preserves_existing_json(self):
        """Failure while opening a stream must not leak its raw descriptor."""
        saves = (
            lambda: utils.save_table_data("users", [{"ID": 2, "name": "Новая"}]),
            lambda: utils.save_metadata(META_FILE, {}),
        )
        for save in saves:
            with self.subTest(save=save):
                before = self.snapshot()
                descriptors = []

                def denied_fdopen(descriptor, *args, **kwargs):
                    descriptors.append(descriptor)
                    raise OSError("stream creation failed")

                with patch.object(utils.os, "fdopen", side_effect=denied_fdopen):
                    with self.assertRaises(OSError):
                        save()

                self.assertEqual(len(descriptors), 1)
                with self.assertRaises(OSError):
                    os.fstat(descriptors[0])
                self.assertEqual(self.snapshot(), before)

    def test_backup_fdopen_failure_closes_descriptor_and_preserves_table(self):
        """An unopened backup stream must be cleaned up before deletion starts."""
        before = self.snapshot()
        descriptors = []

        def denied_fdopen(descriptor, *args, **kwargs):
            descriptors.append(descriptor)
            raise OSError("backup stream creation failed")

        with patch.object(utils.os, "fdopen", side_effect=denied_fdopen):
            result, output = self.drop_table()

        self.assertIs(result, DB_ERROR)
        self.assertIn("Ошибка работы с файлом", output)
        self.assertEqual(len(descriptors), 1)
        with self.assertRaises(OSError):
            os.fstat(descriptors[0])
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.metadata, utils.load_metadata(META_FILE))

    def test_invalid_encoding_preserves_original_error_and_cleans_temporary_file(self):
        """fdopen may close its descriptor before rejecting an unknown encoding."""
        before = self.snapshot()
        with self.assertRaises(LookupError):
            utils._create_temporary_file(
                "test.json", "w", encoding="nonexistent-encoding"
            )
        self.assertEqual(self.snapshot(), before)

    def test_long_table_name_supports_create_insert_and_drop(self):
        """Temporary file names must not exceed the valid target's name limit."""
        table_name = "a" * 240
        before = self.snapshot()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = engine.execute_table_command(
                {
                    "command": "create_table",
                    "table_name": table_name,
                    "columns": ["name:str"],
                },
                self.metadata,
            )
        self.assertIsNot(result, DB_ERROR, output.getvalue())
        self.assertIn(table_name, utils.load_metadata(META_FILE))

        with contextlib.redirect_stdout(output):
            result = engine.execute_data_command(
                {"command": "insert", "table_name": table_name, "values": ["Длинное"]},
                self.metadata,
            )
        self.assertIsNot(result, DB_ERROR, output.getvalue())
        self.assertEqual(
            utils.load_table_data(table_name), [{"ID": 1, "name": "Длинное"}]
        )

        with patch("builtins.input", return_value="y"):
            with contextlib.redirect_stdout(output):
                result = engine.execute_table_command(
                    {"command": "drop_table", "table_name": table_name},
                    self.metadata,
                )
        self.assertIsNot(result, DB_ERROR, output.getvalue())
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.metadata, utils.load_metadata(META_FILE))


if __name__ == "__main__":
    unittest.main()
