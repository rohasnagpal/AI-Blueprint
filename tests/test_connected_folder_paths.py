import asyncio
import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi import BackgroundTasks, HTTPException

import database
from routes.documents import (
    ConnectedFolderIn,
    _normalize_folder_path_input,
    _resolve_folder_path,
    _safe_display_path,
    add_connected_folder,
    sync_connected_folder,
)


class ConnectedFolderPathTest(unittest.TestCase):
    def test_normalizes_macos_absolute_path_without_leading_slash(self) -> None:
        self.assertEqual(
            _normalize_folder_path_input("Users/samairahnagpal/AIBlueprint/"),
            "/Users/samairahnagpal/AIBlueprint/",
        )

    def test_preserves_explicit_relative_path(self) -> None:
        self.assertEqual(_normalize_folder_path_input("./Users/example"), "./Users/example")

    def test_resolves_workspace_path_without_leading_slash(self) -> None:
        workspace = Path(__file__).resolve().parents[1]
        path_without_leading_slash = str(workspace).lstrip("/")

        self.assertEqual(_resolve_folder_path(path_without_leading_slash), str(workspace))

    def test_rejects_blank_path(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            _normalize_folder_path_input("   ")
        self.assertEqual(raised.exception.status_code, 400)

    def test_safe_display_path_preserves_subfolder_path(self) -> None:
        self.assertEqual(
            _safe_display_path("Matter/Subfolder/contract.pdf"),
            "Matter/Subfolder/contract.pdf",
        )

    def test_safe_display_path_removes_parent_segments(self) -> None:
        self.assertEqual(
            _safe_display_path("../Matter/./Subfolder/contract.pdf"),
            "Matter/Subfolder/contract.pdf",
        )

    def test_sync_recurses_subfolders_and_removes_deleted_files(self) -> None:
        original_db_path = database.DB_PATH
        runtime = Path(tempfile.mkdtemp(prefix="aibp-connected-folder-test-"))
        try:
            database.DB_PATH = str(runtime / "legacy.db")
            database.init_db()

            folder = runtime / "source"
            nested = folder / "nested"
            nested.mkdir(parents=True)
            source_file = nested / "contract.txt"
            source_file.write_text("subfolder sync test", encoding="utf-8")

            created = asyncio.run(add_connected_folder(ConnectedFolderIn(path=str(folder))))
            first = asyncio.run(sync_connected_folder(created["id"], BackgroundTasks()))
            self.assertEqual(first["added"], 1)

            conn = database.get_connection()
            docs = conn.execute("SELECT original_name FROM documents").fetchall()
            mappings = conn.execute("SELECT * FROM connected_folder_files").fetchall()
            conn.close()
            self.assertEqual([row["original_name"] for row in docs], ["nested/contract.txt"])
            self.assertEqual(len(mappings), 1)

            source_file.unlink()
            second = asyncio.run(sync_connected_folder(created["id"], BackgroundTasks()))
            self.assertEqual(second["removed"], 1)

            conn = database.get_connection()
            doc_count = conn.execute("SELECT COUNT(*) AS count FROM documents").fetchone()["count"]
            mapping_count = conn.execute("SELECT COUNT(*) AS count FROM connected_folder_files").fetchone()["count"]
            conn.close()
            self.assertEqual(doc_count, 0)
            self.assertEqual(mapping_count, 0)
        finally:
            database.DB_PATH = original_db_path
            shutil.rmtree(runtime, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
