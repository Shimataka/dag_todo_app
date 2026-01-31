import os
import tempfile
import unittest
from pathlib import Path

import pytest

from dandori.core.models import Task
from dandori.io.json_io import export_json, import_json
from dandori.storage.yaml_store import StoreToYAML


def test_export_json_file_exists_raises() -> None:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as f:
        path = f.name
    try:
        with Path(path).open("w") as f:
            f.write("{}")
        with pytest.raises(FileExistsError) as exc_info:
            export_json({}, path)
        assert "already exists" in str(exc_info.value)
    finally:
        Path(path).unlink(missing_ok=True)


def test_import_json_file_not_found_raises() -> None:
    with pytest.raises(FileNotFoundError) as exc_info:
        import_json("/nonexistent/path/to/file.json")
    assert "not found" in str(exc_info.value).lower() or "File not found" in str(exc_info.value)


class TestImportExport(unittest.TestCase):
    """export / import で同一内容に戻ることのテスト"""

    def setUp(self) -> None:
        """各テストの前に一時ファイルを作成"""
        self.original_username = os.environ.get("DD_USERNAME")
        os.environ["DD_USERNAME"] = "test_user"
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".yaml")  # noqa: SIM115
        self.temp_file.close()
        self.store = StoreToYAML(data_path=self.temp_file.name)
        self.store.load()

    def tearDown(self) -> None:
        """各テストの後に一時ファイルを削除"""
        Path(self.temp_file.name).unlink(missing_ok=True)
        if self.original_username is not None:
            os.environ["DD_USERNAME"] = self.original_username
        elif "DD_USERNAME" in os.environ:
            del os.environ["DD_USERNAME"]

    def test_export_import_preserves_content(self) -> None:
        """Export / import で同一内容に戻ることを確認"""
        # 複数のタスクと依存関係を作成
        task_a = Task(id="task_a", title="タスクA", description="説明A", priority=3, owner="test_user")
        task_b = Task(id="task_b", title="タスクB", description="説明B", priority=2, owner="test_user")
        task_c = Task(id="task_c", title="タスクC", description="説明C", priority=1, owner="test_user")
        self.store.add_task(task_a)
        self.store.add_task(task_b)
        self.store.add_task(task_c)
        self.store.link_tasks("task_a", "task_b")
        self.store.link_tasks("task_b", "task_c")
        self.store.save()

        # エクスポート(存在しないファイルを使用)
        fd, export_file = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        Path(export_file).unlink(missing_ok=True)  # ファイルを削除してからエクスポート
        try:
            all_tasks_result = self.store.get_all_tasks()
            assert all_tasks_result.is_ok()
            export_json(all_tasks_result.unwrap(), export_file)

            # 新しいストアを作成してインポート
            new_store = StoreToYAML(data_path=self.temp_file.name + ".new")
            new_store.load()
            imported_tasks = import_json(export_file)

            for tid, task in imported_tasks.items():
                new_store.add_task(task, id_overwritten=tid)
            new_store.save()

            # 元のタスクとインポートしたタスクを比較
            original_tasks_result = self.store.get_all_tasks()
            imported_tasks_result = new_store.get_all_tasks()
            assert original_tasks_result.is_ok()
            assert imported_tasks_result.is_ok()

            original_tasks = original_tasks_result.unwrap()
            imported_tasks_dict = imported_tasks_result.unwrap()

            # タスク数が同じ
            assert len(original_tasks) == len(imported_tasks_dict)

            # 各タスクの内容が同じ
            for tid in original_tasks:
                assert tid in imported_tasks_dict
                orig = original_tasks[tid]
                imported = imported_tasks_dict[tid]

                assert orig.id == imported.id
                assert orig.title == imported.title
                assert orig.description == imported.description
                assert orig.priority == imported.priority
                assert set[str](orig.depends_on) == set[str](imported.depends_on)
                assert set[str](orig.children) == set[str](imported.children)

            # 依存関係も同じ
            for tid in original_tasks:
                orig = original_tasks[tid]
                imported = imported_tasks_dict[tid]
                assert set[str](orig.depends_on) == set[str](imported.depends_on)
                assert set[str](orig.children) == set[str](imported.children)

        finally:
            Path(export_file).unlink(missing_ok=True)
            Path(self.temp_file.name + ".new").unlink(missing_ok=True)

    def test_export_import_preserves_archived_status(self) -> None:
        """アーカイブ状態も保持されることを確認"""
        task_a = Task(id="task_a", title="タスクA", is_archived=True, owner="test_user")
        task_b = Task(id="task_b", title="タスクB", is_archived=False, owner="test_user")
        self.store.add_task(task_a)
        self.store.add_task(task_b)
        self.store.save()

        # エクスポート(存在しないファイルを使用)
        fd, export_file = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        Path(export_file).unlink(missing_ok=True)  # ファイルを削除してからエクスポート
        try:
            all_tasks_result = self.store.get_all_tasks()
            assert all_tasks_result.is_ok()
            export_json(all_tasks_result.unwrap(), export_file)

            # インポート
            imported_tasks = import_json(export_file)

            # アーカイブ状態が保持されている
            assert imported_tasks["task_a"].is_archived
            assert not imported_tasks["task_b"].is_archived

        finally:
            Path(export_file).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
