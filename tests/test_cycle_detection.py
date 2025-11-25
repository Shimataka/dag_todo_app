import os
import tempfile
import unittest
from pathlib import Path

from dandori.core.models import Task
from dandori.storage.yaml_store import StoreToYAML


class TestCycleDetection(unittest.TestCase):
    """循環を起こす link がちゃんとエラーになることのテスト"""

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

    def test_direct_cycle_detection(self) -> None:
        """直接的な循環（A→A）が検出される"""
        task_a = Task(id="task_a", title="タスクA", owner="test_user")
        self.store.add_task(task_a)
        self.store.save()

        # A→Aのリンクを作成しようとするとエラー
        result = self.store.link_tasks("task_a", "task_a")
        assert result.is_err()
        assert "Cycle detected" in result.unwrap_err()

    def test_simple_cycle_detection(self) -> None:
        """シンプルな循環（A→B→A）が検出される"""
        task_a = Task(id="task_a", title="タスクA", owner="test_user")
        task_b = Task(id="task_b", title="タスクB", owner="test_user")
        self.store.add_task(task_a)
        self.store.add_task(task_b)
        self.store.link_tasks("task_a", "task_b")
        self.store.save()

        # B→Aのリンクを作成しようとすると循環が検出される
        result = self.store.link_tasks("task_b", "task_a")
        assert result.is_err()
        assert "Cycle detected" in result.unwrap_err()

    def test_long_cycle_detection(self) -> None:
        """長い循環（A→B→C→A）が検出される"""
        task_a = Task(id="task_a", title="タスクA", owner="test_user")
        task_b = Task(id="task_b", title="タスクB", owner="test_user")
        task_c = Task(id="task_c", title="タスクC", owner="test_user")
        self.store.add_task(task_a)
        self.store.add_task(task_b)
        self.store.add_task(task_c)
        self.store.link_tasks("task_a", "task_b")
        self.store.link_tasks("task_b", "task_c")
        self.store.save()

        # C→Aのリンクを作成しようとすると循環が検出される
        result = self.store.link_tasks("task_c", "task_a")
        assert result.is_err()
        assert "Cycle detected" in result.unwrap_err()

    def test_non_cycle_allowed(self) -> None:
        """循環でないリンクは正常に作成される"""
        task_a = Task(id="task_a", title="タスクA", owner="test_user")
        task_b = Task(id="task_b", title="タスクB", owner="test_user")
        task_c = Task(id="task_c", title="タスクC", owner="test_user")
        self.store.add_task(task_a)
        self.store.add_task(task_b)
        self.store.add_task(task_c)
        self.store.link_tasks("task_a", "task_b")
        self.store.save()

        # B→Cのリンクは循環を作らないので成功
        result = self.store.link_tasks("task_b", "task_c")
        assert result.is_ok()


if __name__ == "__main__":
    unittest.main()
