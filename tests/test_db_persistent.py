import os
import tempfile
import unittest
from pathlib import Path

import yaml

from dandori.core.models import Task
from dandori.storage.sqlite3_store import StoreToSQLite
from dandori.storage.yaml_store import StoreToYAML


class TestYAMLDBPersistent(unittest.TestCase):
    """StoreToYAML の永続化と commit/rollback に関するテスト"""

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

    def test_commit_persists_changes(self) -> None:
        """Commit で変更が _tasks に反映されることを確認"""
        # 初期状態
        task_a = Task(id="task_a", title="タスクA", owner="test_user")
        self.store.add_task(task_a)
        self.store.commit()

        # commit 後、_tasks に反映されている
        assert "task_a" in self.store._tasks  # noqa: SLF001
        assert self.store._tasks["task_a"].title == "タスクA"  # noqa: SLF001

        # _tmp_tasks にも存在する
        assert "task_a" in self.store._tmp_tasks  # noqa: SLF001

    def test_rollback_discards_changes(self) -> None:
        """Rollback で変更が破棄されることを確認"""
        # 初期状態を commit
        task_a = Task(id="task_a", title="タスクA", owner="test_user")
        self.store.add_task(task_a)
        self.store.commit()

        # 新しいタスクを追加(まだ commit していない)
        task_b = Task(id="task_b", title="タスクB", owner="test_user")
        self.store.add_task(task_b)

        # rollback で変更を破棄
        self.store.rollback()

        # task_b は存在しない
        assert "task_b" not in self.store._tmp_tasks  # noqa: SLF001
        assert "task_b" not in self.store._tasks  # noqa: SLF001

        # task_a は保持されている
        assert "task_a" in self.store._tmp_tasks  # noqa: SLF001
        assert "task_a" in self.store._tasks  # noqa: SLF001

    def test_commit_after_rollback_preserves_committed_state(self) -> None:
        """Commit 後に rollback しても、commit した内容は保持される"""
        # 初期状態を commit
        task_a = Task(id="task_a", title="タスクA", owner="test_user")
        self.store.add_task(task_a)
        self.store.commit()

        # 新しいタスクを追加して rollback
        task_b = Task(id="task_b", title="タスクB", owner="test_user")
        self.store.add_task(task_b)
        self.store.rollback()

        # commit した task_a は保持されている
        assert "task_a" in self.store._tasks  # noqa: SLF001
        assert "task_a" in self.store._tmp_tasks  # noqa: SLF001

        # rollback した task_b は存在しない
        assert "task_b" not in self.store._tasks  # noqa: SLF001
        assert "task_b" not in self.store._tmp_tasks  # noqa: SLF001

    def test_save_load_with_commit(self) -> None:
        """Save/load と commit の関係を確認"""
        # タスクを追加して commit
        task_a = Task(id="task_a", title="タスクA", owner="test_user")
        self.store.add_task(task_a)
        self.store.commit()
        self.store.save()

        # 新しいストアインスタンスで読み込み
        new_store = StoreToYAML(data_path=self.temp_file.name)
        new_store.load()

        # タスクが読み込まれている
        result = new_store.get_task("task_a")
        assert result.is_ok()
        assert result.unwrap().title == "タスクA"

    def test_save_load_without_commit(self) -> None:
        """Commit せずに save した場合の動作を確認"""
        # タスクを追加(commit しない)
        task_a = Task(id="task_a", title="タスクA", owner="test_user")
        self.store.add_task(task_a)
        self.store.save()  # commit せずに save

        # 新しいストアインスタンスで読み込み
        new_store = StoreToYAML(data_path=self.temp_file.name)
        new_store.load()

        # save は _tmp_tasks を保存するので、読み込まれる
        result = new_store.get_task("task_a")
        assert result.is_ok()
        assert result.unwrap().title == "タスクA"

    def test_multiple_operations_with_commit_rollback(self) -> None:
        """複数の操作後の commit/rollback を確認"""
        # 初期状態を commit
        task_a = Task(id="task_a", title="タスクA", owner="test_user")
        self.store.add_task(task_a)
        self.store.commit()

        # 複数の操作
        task_b = Task(id="task_b", title="タスクB", owner="test_user")
        task_c = Task(id="task_c", title="タスクC", owner="test_user")
        self.store.add_task(task_b)
        self.store.add_task(task_c)
        self.store.link_tasks("task_a", "task_b")

        # rollback で全ての変更を破棄
        self.store.rollback()

        # task_a のみが存在
        assert "task_a" in self.store._tmp_tasks  # noqa: SLF001
        assert "task_b" not in self.store._tmp_tasks  # noqa: SLF001
        assert "task_c" not in self.store._tmp_tasks  # noqa: SLF001

        # 再度操作して commit
        self.store.add_task(task_b)
        self.store.commit()

        # commit 後、両方存在
        assert "task_a" in self.store._tasks  # noqa: SLF001
        assert "task_b" in self.store._tasks  # noqa: SLF001
        assert "task_c" not in self.store._tasks  # noqa: SLF001

    def test_commit_rollback_with_task_modification(self) -> None:
        """タスクの変更に対する commit/rollback を確認"""
        # 初期状態を commit
        task_a = Task(id="task_a", title="タスクA", priority=1, owner="test_user")
        self.store.add_task(task_a)
        self.store.commit()

        # タスクを変更(まだ commit していない)
        task_a_modified = self.store.get_task("task_a").unwrap()
        task_a_modified.title = "タスクA(変更)"
        task_a_modified.priority = 2
        self.store.tasks["task_a"] = task_a_modified

        # rollback で変更を破棄
        self.store.rollback()

        # 元の状態に戻っている
        task_a_restored = self.store.get_task("task_a").unwrap()
        assert task_a_restored.title == "タスクA"
        assert task_a_restored.priority == 1

        # 再度変更して commit
        task_a_modified2 = self.store.get_task("task_a").unwrap()
        task_a_modified2.title = "タスクA(変更済み)"
        task_a_modified2.priority = 3
        self.store.tasks["task_a"] = task_a_modified2
        self.store.commit()

        # commit 後、変更が反映されている
        task_a_committed = self.store._tasks["task_a"]  # noqa: SLF001
        assert task_a_committed.title == "タスクA(変更済み)"
        assert task_a_committed.priority == 3

    def test_commit_rollback_with_task_removal(self) -> None:
        """タスクの削除に対する commit/rollback を確認"""
        # 初期状態を commit
        task_a = Task(id="task_a", title="タスクA", owner="test_user")
        task_b = Task(id="task_b", title="タスクB", owner="test_user")
        self.store.add_task(task_a)
        self.store.add_task(task_b)
        self.store.commit()

        # タスクを削除(まだ commit していない)
        self.store.remove_task("task_b")

        # rollback で変更を破棄
        self.store.rollback()

        # task_b が復元されている
        result = self.store.get_task("task_b")
        assert result.is_ok()

        # 再度削除して commit
        self.store.remove_task("task_b")
        self.store.commit()

        # commit 後、task_b は存在しない
        assert "task_b" not in self.store._tasks  # noqa: SLF001
        assert "task_b" not in self.store._tmp_tasks  # noqa: SLF001

    def test_deep_copy_isolation(self) -> None:
        """Commit/rollback で deepcopy が正しく動作することを確認"""
        # 初期状態を commit
        task_a = Task(id="task_a", title="タスクA", owner="test_user")
        self.store.add_task(task_a)
        self.store.commit()

        # _tmp_tasks のタスクを変更
        task_a_tmp = self.store._tmp_tasks["task_a"]  # noqa: SLF001
        task_a_tmp.title = "変更されたタイトル"

        # _tasks のタスクは変更されていない(deepcopy の確認)
        assert self.store._tasks["task_a"].title == "タスクA"  # noqa: SLF001
        assert self.store._tmp_tasks["task_a"].title == "変更されたタイトル"  # noqa: SLF001

        # rollback で元に戻る
        self.store.rollback()
        assert self.store._tmp_tasks["task_a"].title == "タスクA"  # noqa: SLF001

    def test_persistence_through_file(self) -> None:
        """ファイルを通じた永続化を確認"""
        # タスクを追加して commit と save
        task_a = Task(id="task_a", title="タスクA", owner="test_user")
        task_b = Task(id="task_b", title="タスクB", owner="test_user")
        self.store.add_task(task_a)
        self.store.add_task(task_b)
        self.store.link_tasks("task_a", "task_b")
        self.store.commit()
        self.store.save()

        # ファイルの内容を直接確認
        with Path(self.temp_file.name).open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
            assert "tasks" in data
            assert "task_a" in data["tasks"]
            assert "task_b" in data["tasks"]
            assert data["tasks"]["task_a"]["title"] == "タスクA"
            assert data["tasks"]["task_b"]["title"] == "タスクB"

        # 新しいストアインスタンスで読み込み
        new_store = StoreToYAML(data_path=self.temp_file.name)
        new_store.load()

        # タスクとリンクが正しく読み込まれている
        task_a_result = new_store.get_task("task_a")
        task_b_result = new_store.get_task("task_b")
        assert task_a_result.is_ok()
        assert task_b_result.is_ok()

        task_a_loaded = task_a_result.unwrap()
        task_b_loaded = task_b_result.unwrap()
        assert "task_b" in task_a_loaded.children
        assert "task_a" in task_b_loaded.depends_on


class TestSQLiteDBPersistent(unittest.TestCase):
    """StoreToSQLite の永続化と commit/rollback に関するテスト"""

    def setUp(self) -> None:
        """各テストの前に一時ファイルを作成"""
        self.original_username = os.environ.get("DD_USERNAME")
        os.environ["DD_USERNAME"] = "test_user"
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".yaml")  # noqa: SIM115
        self.temp_file.close()
        self.store = StoreToSQLite(data_path=self.temp_file.name)
        self.store.load()

    def tearDown(self) -> None:
        """各テストの後に一時ファイルを削除"""
        Path(self.temp_file.name).unlink(missing_ok=True)
        if self.original_username is not None:
            os.environ["DD_USERNAME"] = self.original_username
        elif "DD_USERNAME" in os.environ:
            del os.environ["DD_USERNAME"]

    def test_commit_persists_changes(self) -> None:
        """Commit で変更が _tasks に反映されることを確認"""
        # 初期状態
        task_a = Task(id="task_a", title="タスクA", owner="test_user")
        self.store.add_task(task_a)
        self.store.commit()

        # commit 後、_tasks に反映されている
        result = self.store.get_task("task_a")
        assert result.is_ok()
        assert result.unwrap().title == "タスクA"

    def test_rollback_discards_changes(self) -> None:
        """Rollback で変更が破棄されることを確認"""
        # 初期状態を commit
        task_a = Task(id="task_a", title="タスクA", owner="test_user")
        self.store.add_task(task_a)
        self.store.commit()

        # 新しいタスクを追加(まだ commit していない)
        task_b = Task(id="task_b", title="タスクB", owner="test_user")
        self.store.add_task(task_b)

        # rollback で変更を破棄
        self.store.rollback()

        # task_b は存在しない
        result = self.store.get_task("task_b")
        assert result.is_err()
        assert "not found" in result.unwrap_err()

        # task_a は保持されている
        result = self.store.get_task("task_a")
        assert result.is_ok()
        assert result.unwrap().title == "タスクA"

    def test_commit_after_rollback_preserves_committed_state(self) -> None:
        """Commit 後に rollback しても、commit した内容は保持される"""
        # 初期状態を commit
        task_a = Task(id="task_a", title="タスクA", owner="test_user")
        self.store.add_task(task_a)
        self.store.commit()

        # 新しいタスクを追加して rollback
        task_b = Task(id="task_b", title="タスクB", owner="test_user")
        self.store.add_task(task_b)
        self.store.rollback()

        # commit した task_a は保持されている
        result = self.store.get_task("task_a")
        assert result.is_ok()
        assert result.unwrap().title == "タスクA"

        # rollback した task_b は存在しない
        result = self.store.get_task("task_b")
        assert result.is_err()
        assert "not found" in result.unwrap_err()

    def test_save_load_with_commit(self) -> None:
        """Save/load と commit の関係を確認"""
        # タスクを追加して commit
        task_a = Task(id="task_a", title="タスクA", owner="test_user")
        self.store.add_task(task_a)
        self.store.commit()
        self.store.save()

        # 新しいストアインスタンスで読み込み
        new_store = StoreToSQLite(data_path=self.temp_file.name)
        new_store.load()

        # タスクが読み込まれている
        result = new_store.get_task("task_a")
        assert result.is_ok()
        assert result.unwrap().title == "タスクA"

    def test_save_load_without_commit(self) -> None:
        """Commit せずに save した場合の動作を確認"""
        # タスクを追加(commit しない)
        task_a = Task(id="task_a", title="タスクA", owner="test_user")
        self.store.add_task(task_a)
        self.store.save()  # commit せずに save

        # 新しいストアインスタンスで読み込み
        new_store = StoreToSQLite(data_path=self.temp_file.name)
        new_store.load()

        # save は _tmp_tasks を保存するので、読み込まれる
        result = new_store.get_task("task_a")
        assert result.is_ok()
        assert result.unwrap().title == "タスクA"

    def test_multiple_operations_with_commit_rollback(self) -> None:
        """複数の操作後の commit/rollback を確認"""
        # 初期状態を commit
        task_a = Task(id="task_a", title="タスクA", owner="test_user")
        self.store.add_task(task_a)
        self.store.commit()

        # 複数の操作
        task_b = Task(id="task_b", title="タスクB", owner="test_user")
        task_c = Task(id="task_c", title="タスクC", owner="test_user")
        self.store.add_task(task_b)
        self.store.add_task(task_c)
        self.store.link_tasks("task_a", "task_b")

        # rollback で全ての変更を破棄
        self.store.rollback()

        # task_a のみが存在
        result = self.store.get_task("task_a")
        assert result.is_ok()
        assert result.unwrap().title == "タスクA"
        result = self.store.get_task("task_b")
        assert result.is_err()
        assert "not found" in result.unwrap_err()
        result = self.store.get_task("task_c")
        assert result.is_err()
        assert "not found" in result.unwrap_err()

        # 再度操作して commit
        self.store.add_task(task_b)
        self.store.commit()

        # commit 後、両方存在
        result = self.store.get_task("task_a")
        assert result.is_ok()
        assert result.unwrap().title == "タスクA"
        result = self.store.get_task("task_b")
        assert result.is_ok()
        assert result.unwrap().title == "タスクB"
        result = self.store.get_task("task_c")
        assert result.is_err()
        assert "not found" in result.unwrap_err()

    def test_commit_rollback_with_task_modification(self) -> None:
        """タスクの変更に対する commit/rollback を確認"""
        # 初期状態を commit
        task_a = Task(id="task_a", title="タスクA", priority=1, owner="test_user")
        self.store.add_task(task_a)
        self.store.commit()

        # タスクを変更(まだ commit していない)
        task_a_modified = self.store.get_task("task_a").unwrap()
        task_a_modified.title = "タスクA(変更)"
        task_a_modified.priority = 2
        self.store.update_task(task_a_modified)

        # rollback で変更を破棄
        self.store.rollback()

        # 元の状態に戻っている
        task_a_restored = self.store.get_task("task_a").unwrap()
        assert task_a_restored.title == "タスクA"
        assert task_a_restored.priority == 1

        # 再度変更して commit
        task_a_modified2 = self.store.get_task("task_a").unwrap()
        task_a_modified2.title = "タスクA(変更済み)"
        task_a_modified2.priority = 3
        self.store.update_task(task_a_modified2)
        self.store.commit()

        # commit 後、変更が反映されている
        task_a_committed = self.store.get_task("task_a").unwrap()
        assert task_a_committed.title == "タスクA(変更済み)"
        assert task_a_committed.priority == 3

    def test_commit_rollback_with_task_removal(self) -> None:
        """タスクの削除に対する commit/rollback を確認"""
        # 初期状態を commit
        task_a = Task(id="task_a", title="タスクA", owner="test_user")
        task_b = Task(id="task_b", title="タスクB", owner="test_user")
        self.store.add_task(task_a)
        self.store.add_task(task_b)
        self.store.commit()

        # タスクを削除(まだ commit していない)
        self.store.remove_task("task_b")

        # rollback で変更を破棄
        self.store.rollback()

        # task_b が復元されている
        result = self.store.get_task("task_b")
        assert result.is_ok()

        # 再度削除して commit
        self.store.remove_task("task_b")
        self.store.commit()

        # commit 後、task_b は存在しない
        result = self.store.get_task("task_b")
        assert result.is_err()
        assert "not found" in result.unwrap_err()

    def test_deep_copy_isolation(self) -> None:
        """Commit/rollback で deepcopy が正しく動作することを確認"""
        # 初期状態を commit
        task_a = Task(id="task_a", title="タスクA", owner="test_user")
        self.store.add_task(task_a)
        self.store.commit()

        # _tmp_tasks のタスクを変更
        task_a_tmp = self.store.get_task("task_a").unwrap()
        task_a_tmp.title = "変更されたタイトル"

        # _tasks のタスクは変更されていない(deepcopy の確認)
        assert self.store.get_task("task_a").unwrap().title == "タスクA"
        assert task_a_tmp.title == "変更されたタイトル"

        # rollback で元に戻る
        self.store.rollback()
        assert self.store.get_task("task_a").unwrap().title == "タスクA"


if __name__ == "__main__":
    unittest.main()
