import tempfile
import unittest
from pathlib import Path

from dandori.core.models import Task
from dandori.storage.yaml_store import StoreToYAML


class TestArchiveComponent(unittest.TestCase):
    """archive_component が弱連結成分単位で動いていることのテスト"""

    def setUp(self) -> None:
        """各テストの前に一時ファイルを作成"""
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".yaml")  # noqa: SIM115
        self.temp_file.close()
        self.store = StoreToYAML(data_path=self.temp_file.name)
        self.store.load()

    def tearDown(self) -> None:
        """各テストの後に一時ファイルを削除"""
        Path(self.temp_file.name).unlink(missing_ok=True)

    def test_archive_component_archives_connected_tasks(self) -> None:
        """弱連結成分の全タスクがアーカイブされることを確認"""
        # A→B→Cの構造を作成
        task_a = Task(id="task_a", title="タスクA")
        task_b = Task(id="task_b", title="タスクB")
        task_c = Task(id="task_c", title="タスクC")
        self.store.add_task(task_a)
        self.store.add_task(task_b)
        self.store.add_task(task_c)
        self.store.link("task_a", "task_b")
        self.store.link("task_b", "task_c")
        self.store.save()

        # 初期状態ではアーカイブされていない
        assert self.store.get("task_a").unwrap().is_archived is False
        assert self.store.get("task_b").unwrap().is_archived is False
        assert self.store.get("task_c").unwrap().is_archived is False

        # task_bを含む弱連結成分をアーカイブ
        archive_result = self.store.archive_component("task_b", flag=True)
        assert archive_result.is_ok()
        archived_ids = archive_result.unwrap()
        self.store.save()

        # A, B, Cすべてがアーカイブされている
        assert "task_a" in archived_ids
        assert "task_b" in archived_ids
        assert "task_c" in archived_ids

        assert self.store.get("task_a").unwrap().is_archived is True
        assert self.store.get("task_b").unwrap().is_archived is True
        assert self.store.get("task_c").unwrap().is_archived is True

    def test_archive_component_does_not_affect_disconnected_tasks(self) -> None:
        """連結していないタスクはアーカイブされないことを確認"""
        # A→Bのグループと、Cの独立タスクを作成
        task_a = Task(id="task_a", title="タスクA")
        task_b = Task(id="task_b", title="タスクB")
        task_c = Task(id="task_c", title="タスクC")
        self.store.add_task(task_a)
        self.store.add_task(task_b)
        self.store.add_task(task_c)
        self.store.link("task_a", "task_b")
        self.store.save()

        # task_aを含む弱連結成分をアーカイブ
        archive_result = self.store.archive_component("task_a", flag=True)
        assert archive_result.is_ok()
        archived_ids = archive_result.unwrap()
        self.store.save()

        # AとBはアーカイブされているが、Cはされていない
        assert "task_a" in archived_ids
        assert "task_b" in archived_ids
        assert "task_c" not in archived_ids

        assert self.store.get("task_a").unwrap().is_archived is True
        assert self.store.get("task_b").unwrap().is_archived is True
        assert self.store.get("task_c").unwrap().is_archived is False

    def test_unarchive_component_restores_connected_tasks(self) -> None:
        """弱連結成分の全タスクが復元されることを確認"""
        # A→Bの構造を作成してアーカイブ
        task_a = Task(id="task_a", title="タスクA", is_archived=True)
        task_b = Task(id="task_b", title="タスクB", is_archived=True)
        self.store.add_task(task_a)
        self.store.add_task(task_b)
        self.store.link("task_a", "task_b")
        self.store.save()

        # 復元
        restore_result = self.store.archive_component("task_a", flag=False)
        assert restore_result.is_ok()
        restored_ids = restore_result.unwrap()
        self.store.save()

        # AとBが復元されている
        assert "task_a" in restored_ids
        assert "task_b" in restored_ids

        assert self.store.get("task_a").unwrap().is_archived is False
        assert self.store.get("task_b").unwrap().is_archived is False


if __name__ == "__main__":
    unittest.main()
