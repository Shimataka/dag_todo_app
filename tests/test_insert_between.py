import os
import tempfile
import unittest
from pathlib import Path

from dandori.core.models import Task
from dandori.storage.yaml_store import StoreToYAML


class TestInsertBetween(unittest.TestCase):
    """insert_between で A→C→B になることのテスト"""

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

    def test_insert_between_creates_a_to_c_to_b(self) -> None:
        """insert_between で A→C→B の構造ができることを確認"""
        # AとBのタスクを作成
        task_a = Task(id="task_a", title="タスクA", owner="test_user")
        task_b = Task(id="task_b", title="タスクB", owner="test_user")
        self.store.add_task(task_a)
        self.store.add_task(task_b)

        # A→Bのリンクを作成
        link_result = self.store.link_tasks("task_a", "task_b")
        assert link_result.is_ok()
        self.store.save()

        # A→Bのリンクが存在することを確認
        task_a_result = self.store.get_task("task_a")
        assert task_a_result.is_ok()
        assert "task_b" in task_a_result.unwrap().children

        # CをAとBの間に挿入
        task_c = Task(id="task_c", title="タスクC", owner="test_user")
        insert_result = self.store.insert_task("task_a", "task_b", task_c)
        assert insert_result.is_ok()
        self.store.save()

        # A→C→Bの構造になっていることを確認
        task_a_updated = self.store.get_task("task_a").unwrap()
        task_c_updated = self.store.get_task("task_c").unwrap()
        task_b_updated = self.store.get_task("task_b").unwrap()

        # Aの子はCである
        assert "task_c" in task_a_updated.children
        assert "task_b" not in task_a_updated.children

        # Cの親はA、子はBである
        assert "task_a" in task_c_updated.depends_on
        assert "task_b" in task_c_updated.children

        # Bの親はCである
        assert "task_c" in task_b_updated.depends_on
        assert "task_a" not in task_b_updated.depends_on

    def test_insert_between_without_existing_edge(self) -> None:
        """既存のエッジがなくても insert_between が動作する"""
        # AとBのタスクを作成(リンクなし)
        task_a = Task(id="task_a", title="タスクA", owner="test_user")
        task_b = Task(id="task_b", title="タスクB", owner="test_user")
        self.store.add_task(task_a)
        self.store.add_task(task_b)
        self.store.save()

        # CをAとBの間に挿入(エッジがなくても動作)
        task_c = Task(id="task_c", title="タスクC", owner="test_user")
        insert_result = self.store.insert_task("task_a", "task_b", task_c)
        assert insert_result.is_ok()
        self.store.save()

        # A→C→Bの構造になっていることを確認
        task_a_updated = self.store.get_task("task_a").unwrap()
        task_c_updated = self.store.get_task("task_c").unwrap()
        task_b_updated = self.store.get_task("task_b").unwrap()

        assert "task_c" in task_a_updated.children
        assert "task_a" in task_c_updated.depends_on
        assert "task_b" in task_c_updated.children
        assert "task_c" in task_b_updated.depends_on


if __name__ == "__main__":
    unittest.main()
