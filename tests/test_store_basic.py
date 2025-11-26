import os
import tempfile
import unittest
from pathlib import Path

from dandori.core.models import Task
from dandori.storage.yaml_store import StoreToYAML


class TestStoreBasic(unittest.TestCase):
    """基本的なStore操作のテスト: add → list → show の一連の流れ"""

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

    def test_add_list_show_flow(self) -> None:
        """Add → list → show の一連の流れをテスト"""
        # 1. タスクを追加
        task = Task(
            id="test_task_1",
            title="テストタスク",
            description="これはテストです",
            priority=2,
            owner="test_user",
        )
        result = self.store.add_task(task)
        assert result.is_ok()
        self.store.save()

        # 2. リストで取得
        all_tasks_result = self.store.get_all_tasks()
        assert all_tasks_result.is_ok()
        tasks = all_tasks_result.unwrap()
        assert "test_task_1" in tasks
        assert tasks["test_task_1"].title == "テストタスク"

        # 3. showで個別取得
        task_result = self.store.get_task("test_task_1")
        assert task_result.is_ok()
        retrieved_task = task_result.unwrap()
        assert retrieved_task.id == "test_task_1"
        assert retrieved_task.title == "テストタスク"
        assert retrieved_task.description == "これはテストです"
        assert retrieved_task.priority == 2

    def test_add_duplicate_id_fails(self) -> None:
        """同じIDでタスクを追加しようとするとエラーになる"""
        task1 = Task(id="duplicate_id", title="最初のタスク", owner="test_user")
        result1 = self.store.add_task(task1)
        assert result1.is_ok()

        task2 = Task(id="duplicate_id", title="重複タスク", owner="test_user")
        result2 = self.store.add_task(task2)
        assert result2.is_err()
        assert "already exists" in result2.unwrap_err()

    def test_get_nonexistent_task_fails(self) -> None:
        """存在しないタスクを取得しようとするとエラーになる"""
        result = self.store.get_task("nonexistent_id")
        assert result.is_err()
        assert "not found" in result.unwrap_err()


if __name__ == "__main__":
    unittest.main()
