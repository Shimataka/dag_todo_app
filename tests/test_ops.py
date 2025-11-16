import os
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

import pytest

from dandori.core import ops


class TestOps(unittest.TestCase):
    """ops モジュールのユースケース関数のテスト"""

    def setUp(self) -> None:
        """各テストの前に一時ファイルを作成し、環境変数を設定"""
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".yaml")  # noqa: SIM115
        self.temp_file.close()
        self.original_data_path = os.environ.get("DATA_PATH")
        self.original_username = os.environ.get("USERNAME")
        os.environ["DATA_PATH"] = self.temp_file.name
        os.environ["USERNAME"] = "test_user"

    def tearDown(self) -> None:
        """各テストの後に一時ファイルを削除し、環境変数を復元"""
        Path(self.temp_file.name).unlink(missing_ok=True)
        if self.original_data_path is not None:
            os.environ["DATA_PATH"] = self.original_data_path
        elif "DATA_PATH" in os.environ:
            del os.environ["DATA_PATH"]
        if self.original_username is not None:
            os.environ["USERNAME"] = self.original_username
        elif "USERNAME" in os.environ:
            del os.environ["USERNAME"]

    # ---- 一覧取得 / 個別取得 ----

    def test_list_tasks_empty(self) -> None:
        """空のタスクリストを取得できることを確認"""
        tasks = ops.list_tasks()
        assert tasks == []

    def test_list_tasks_with_status_filter(self) -> None:
        """Status フィルタでタスクを取得できることを確認"""
        task1 = ops.add_task([], "タスク1", priority=1)
        task2 = ops.add_task([], "タスク2", priority=2)
        ops.set_status(task1.id, "done")

        pending_tasks = ops.list_tasks(status="pending")
        assert len(pending_tasks) == 1
        assert pending_tasks[0].id == task2.id

        done_tasks = ops.list_tasks(status="done")
        assert len(done_tasks) == 1
        assert done_tasks[0].id == task1.id

    def test_list_tasks_with_archived_filter(self) -> None:
        """Archived フィルタでタスクを取得できることを確認"""
        task1 = ops.add_task([], "タスク1")
        task2 = ops.add_task([], "タスク2")
        archived_ids = ops.archive_tree(task1.id)
        assert task1.id in archived_ids

        archived_tasks = ops.list_tasks(archived=True)
        archived_task_ids = [t.id for t in archived_tasks]
        assert task1.id in archived_task_ids

        active_tasks = ops.list_tasks(archived=False)
        active_task_ids = [t.id for t in active_tasks]
        assert task2.id in active_task_ids
        assert task1.id not in active_task_ids

    def test_list_tasks_with_requested_only(self) -> None:
        """requested_only フィルタでタスクを取得できることを確認"""
        task1 = ops.add_task([], "タスク1")
        ops.add_task([], "タスク2")
        ops.set_requested(task1.id, requested_to="user1", due=None)

        requested_tasks = ops.list_tasks(requested_only=True)
        assert len(requested_tasks) == 1
        assert requested_tasks[0].id == task1.id

    def test_list_tasks_with_topo_sort(self) -> None:
        """Topo ソートでタスクを取得できることを確認"""
        task1 = ops.add_task([], "タスク1")
        task2 = ops.add_task([task1.id], "タスク2")
        task3 = ops.add_task([task2.id], "タスク3")

        tasks = ops.list_tasks(topo=True)
        task_ids = [t.id for t in tasks]
        assert task_ids.index(task1.id) < task_ids.index(task2.id)
        assert task_ids.index(task2.id) < task_ids.index(task3.id)

    def test_get_task_success(self) -> None:
        """存在するタスクを取得できることを確認"""
        task = ops.add_task([], "テストタスク", description="説明", priority=3)
        retrieved = ops.get_task(task.id)
        assert retrieved.id == task.id
        assert retrieved.title == "テストタスク"
        assert retrieved.description == "説明"
        assert retrieved.priority == 3

    def test_get_task_not_found(self) -> None:
        """存在しないタスクを取得しようとすると OpsError が発生することを確認"""
        with pytest.raises(ops.OpsError) as exec_info:
            ops.get_task("nonexistent")
        assert "Task not found" in str(exec_info.value)

    # ---- 追加 / 更新 ----

    def test_add_task_root(self) -> None:
        """ルートタスクを追加できることを確認"""
        task = ops.add_task([], "ルートタスク", description="説明", priority=2)
        assert task.title == "ルートタスク"
        assert task.description == "説明"
        assert task.priority == 2
        assert task.depends_on == []
        assert task.status == "pending"

    def test_add_task_with_parent(self) -> None:
        """親タスクを持つタスクを追加できることを確認"""
        parent = ops.add_task([], "親タスク")
        child = ops.add_task([parent.id], "子タスク")
        assert parent.id in child.depends_on
        parent_updated = ops.get_task(parent.id)
        assert child.id in parent_updated.children

    def test_add_task_with_multiple_parents(self) -> None:
        """複数の親タスクを持つタスクを追加できることを確認"""
        parent1 = ops.add_task([], "親1")
        parent2 = ops.add_task([], "親2")
        child = ops.add_task([parent1.id, parent2.id], "子タスク")
        assert parent1.id in child.depends_on
        assert parent2.id in child.depends_on
        parent1_updated = ops.get_task(parent1.id)
        parent2_updated = ops.get_task(parent2.id)
        assert child.id in parent1_updated.children
        assert child.id in parent2_updated.children

    def test_add_task_with_overwrite_id(self) -> None:
        """overwrite_id_by で ID を指定できることを確認"""
        task = ops.add_task([], "タスク", overwrite_id_by="custom_id")
        assert task.id == "custom_id"

    def test_add_task_with_dates(self) -> None:
        """日付を指定してタスクを追加できることを確認"""
        start = date(2024, 1, 1)
        due = datetime(2024, 12, 31, 23, 59, 59)  # noqa: DTZ001
        task = ops.add_task([], "タスク", start=start, due=due)
        assert task.start_date == "2024-01-01"
        assert task.due_date == "2024-12-31T23:59:59"

    def test_add_task_with_tags(self) -> None:
        """タグを指定してタスクを追加できることを確認"""
        task = ops.add_task([], "タスク", tags=["tag1", "tag2"])
        assert task.tags == ["tag1", "tag2"]

    def test_update_task_title(self) -> None:
        """タスクのタイトルを更新できることを確認"""
        task = ops.add_task([], "元のタイトル")
        updated = ops.update_task(task.id, title="新しいタイトル")
        assert updated.title == "新しいタイトル"

    def test_update_task_description(self) -> None:
        """タスクの説明を更新できることを確認"""
        task = ops.add_task([], "タスク", description="元の説明")
        updated = ops.update_task(task.id, description="新しい説明")
        assert updated.description == "新しい説明"

    def test_update_task_priority(self) -> None:
        """タスクの優先度を更新できることを確認"""
        task = ops.add_task([], "タスク", priority=1)
        updated = ops.update_task(task.id, priority=5)
        assert updated.priority == 5

    def test_update_task_dates(self) -> None:
        """タスクの日付を更新できることを確認"""
        task = ops.add_task([], "タスク")
        start = date(2024, 6, 1)
        due = datetime(2024, 6, 30, 12, 0, 0)  # noqa: DTZ001
        updated = ops.update_task(task.id, start=start, due=due)
        assert updated.start_date == "2024-06-01"
        assert updated.due_date == "2024-06-30T12:00:00"

    def test_update_task_tags(self) -> None:
        """タスクのタグを更新できることを確認"""
        task = ops.add_task([], "タスク", tags=["tag1"])
        updated = ops.update_task(task.id, tags=["tag2", "tag3"])
        assert updated.tags == ["tag2", "tag3"]

    def test_update_task_not_found(self) -> None:
        """存在しないタスクを更新しようとすると OpsError が発生することを確認"""
        with pytest.raises(ops.OpsError) as exec_info:
            ops.update_task("nonexistent", title="タイトル")
        assert "Task not found" in str(exec_info.value)

    # ---- 状態変更 ----

    def test_set_status(self) -> None:
        """タスクのステータスを変更できることを確認"""
        task = ops.add_task([], "タスク")
        updated = ops.set_status(task.id, "in_progress")
        assert updated.status == "in_progress"

        updated = ops.set_status(task.id, "done")
        assert updated.status == "done"

    def test_set_status_not_found(self) -> None:
        """存在しないタスクのステータスを変更しようとすると OpsError が発生することを確認"""
        with pytest.raises(ops.OpsError) as exec_info:
            ops.set_status("nonexistent", "done")
        assert "Task not found" in str(exec_info.value)

    def test_set_requested(self) -> None:
        """タスクを requested 状態に変更できることを確認"""
        task = ops.add_task([], "タスク")
        due = datetime(2024, 12, 31, 23, 59, 59)  # noqa: DTZ001
        updated = ops.set_requested(
            task.id,
            requested_to="assignee",
            due=due,
            note="メモ",
            requested_by="requester",
        )
        assert updated.status == "requested"
        assert updated.assigned_to == "assignee"
        assert updated.requested_by == "requester"
        assert updated.requested_note == "[request-note] メモ"
        assert updated.due_date == "2024-12-31T23:59:59"

    def test_set_requested_without_due(self) -> None:
        """Due なしでタスクを requested 状態に変更できることを確認"""
        task = ops.add_task([], "タスク", due=datetime(2024, 1, 1, 0, 0, 0))  # noqa: DTZ001
        updated = ops.set_requested(task.id, requested_to="assignee", due=None)
        assert updated.status == "requested"
        assert updated.assigned_to == "assignee"
        # due が None の場合は既存の due_date は保持される(上書きされない)
        assert updated.due_date is not None

    def test_set_requested_not_found(self) -> None:
        """存在しないタスクを requested 状態に変更しようとすると OpsError が発生することを確認"""
        with pytest.raises(ops.OpsError) as exec_info:
            ops.set_requested("nonexistent", requested_to="assignee", due=None)
        assert "Task not found" in str(exec_info.value)

    def test_archive_tree(self) -> None:
        """弱連結成分単位でタスクをアーカイブできることを確認"""
        task1 = ops.add_task([], "タスク1")
        task2 = ops.add_task([task1.id], "タスク2")
        task3 = ops.add_task([task2.id], "タスク3")

        archived_ids = ops.archive_tree(task2.id)
        assert task1.id in archived_ids
        assert task2.id in archived_ids
        assert task3.id in archived_ids

        # アーカイブされたタスクを再取得して確認
        task1_archived = ops.get_task(task1.id)
        task2_archived = ops.get_task(task2.id)
        task3_archived = ops.get_task(task3.id)
        assert task1_archived.is_archived is True
        assert task2_archived.is_archived is True
        assert task3_archived.is_archived is True

    def test_archive_tree_not_found(self) -> None:
        """存在しないタスクをアーカイブしようとすると OpsError が発生することを確認"""
        error_raised = False
        try:
            ops.archive_tree("nonexistent")
        except ops.OpsError:
            error_raised = True
        assert error_raised

    def test_unarchive_tree(self) -> None:
        """弱連結成分単位でタスクをアーカイブ解除できることを確認"""
        task1 = ops.add_task([], "タスク1")
        task2 = ops.add_task([task1.id], "タスク2")
        ops.archive_tree(task1.id)

        unarchived_ids = ops.unarchive_tree(task2.id)
        assert task1.id in unarchived_ids
        assert task2.id in unarchived_ids

        task1_unarchived = ops.get_task(task1.id)
        task2_unarchived = ops.get_task(task2.id)
        assert task1_unarchived.is_archived is False
        assert task2_unarchived.is_archived is False

    def test_unarchive_tree_not_found(self) -> None:
        """存在しないタスクをアーカイブ解除しようとすると OpsError が発生することを確認"""
        error_raised = False
        try:
            ops.unarchive_tree("nonexistent")
        except ops.OpsError:
            error_raised = True
        assert error_raised

    # ---- 依存関係取得 ----

    def test_get_deps(self) -> None:
        """タスクの依存関係を取得できることを確認"""
        parent1 = ops.add_task([], "親1")
        parent2 = ops.add_task([], "親2")
        child = ops.add_task([parent1.id, parent2.id], "子")

        deps = ops.get_deps(child.id)
        dep_ids = [d.id for d in deps]
        assert parent1.id in dep_ids
        assert parent2.id in dep_ids
        assert len(deps) == 2

    def test_get_deps_no_parents(self) -> None:
        """親のないタスクの依存関係を取得できることを確認"""
        task = ops.add_task([], "タスク")
        deps = ops.get_deps(task.id)
        assert deps == []

    def test_get_deps_not_found(self) -> None:
        """存在しないタスクの依存関係を取得しようとすると OpsError が発生することを確認"""
        with pytest.raises(ops.OpsError) as exec_info:
            ops.get_deps("nonexistent")
        assert "Task not found" in str(exec_info.value)

    def test_get_children(self) -> None:
        """タスクの子タスクを取得できることを確認"""
        parent = ops.add_task([], "親")
        child1 = ops.add_task([parent.id], "子1")
        child2 = ops.add_task([parent.id], "子2")

        children = ops.get_children(parent.id)
        child_ids = [c.id for c in children]
        assert child1.id in child_ids
        assert child2.id in child_ids
        assert len(children) == 2

    def test_get_children_no_children(self) -> None:
        """子のないタスクの子タスクを取得できることを確認"""
        task = ops.add_task([], "タスク")
        children = ops.get_children(task.id)
        assert children == []

    def test_get_children_not_found(self) -> None:
        """存在しないタスクの子タスクを取得しようとすると OpsError が発生することを確認"""
        with pytest.raises(ops.OpsError) as exec_info:
            ops.get_children("nonexistent")
        assert "Task not found" in str(exec_info.value)

    # ---- DAG 途中挿入 ----

    def test_insert_between(self) -> None:
        """親子の間にタスクを挿入できることを確認"""
        parent = ops.add_task([], "親")
        child = ops.add_task([parent.id], "子")

        # 親子関係が存在することを確認
        parent_before = ops.get_task(parent.id)
        assert child.id in parent_before.children

        new_task = ops.insert_between(
            parent.id,
            child.id,
            title="中間タスク",
            description="説明",
            priority=3,
        )
        assert new_task.title == "中間タスク"
        assert new_task.description == "説明"
        assert new_task.priority == 3

        # 親子関係が正しく更新されていることを確認
        parent_updated = ops.get_task(parent.id)
        new_task_updated = ops.get_task(new_task.id)
        child_updated = ops.get_task(child.id)

        assert new_task.id in parent_updated.children
        assert child.id not in parent_updated.children
        assert parent.id in new_task_updated.depends_on
        assert child.id in new_task_updated.children
        assert new_task.id in child_updated.depends_on
        assert parent.id not in child_updated.depends_on

    def test_insert_between_not_found(self) -> None:
        """存在しない親または子の間にタスクを挿入しようとすると OpsError が発生することを確認"""
        task = ops.add_task([], "タスク")
        with pytest.raises(ops.OpsError) as exec_info:
            ops.insert_between("nonexistent", task.id, title="中間")
        assert "not found" in str(exec_info.value)

        with pytest.raises(ops.OpsError) as exec_info:
            ops.insert_between(task.id, "nonexistent", title="中間")
        assert "not found" in str(exec_info.value)

    # ---- 親追加ユースケース ----

    def test_link_parents(self) -> None:
        """既存タスクに親を追加できることを確認"""
        parent1 = ops.add_task([], "親1")
        parent2 = ops.add_task([], "親2")
        child = ops.add_task([], "子")

        updated = ops.link_parents(child.id, [parent1.id, parent2.id])
        assert parent1.id in updated.depends_on
        assert parent2.id in updated.depends_on
        parent1_updated = ops.get_task(parent1.id)
        parent2_updated = ops.get_task(parent2.id)
        assert child.id in parent1_updated.children
        assert child.id in parent2_updated.children

    def test_link_parents_not_found(self) -> None:
        """存在しないタスクに親を追加しようとすると OpsError が発生することを確認"""
        parent = ops.add_task([], "親")
        with pytest.raises(ops.OpsError) as exec_info:
            ops.link_parents("nonexistent", [parent.id])
        assert "Child task not found" in str(exec_info.value)

        with pytest.raises(ops.OpsError) as exec_info:
            ops.link_parents(parent.id, ["nonexistent"])
        assert "Parent task not found" in str(exec_info.value)

    def test_remove_parent(self) -> None:
        """親子関係を削除できることを確認"""
        parent = ops.add_task([], "親")
        child = ops.add_task([parent.id], "子")

        ops.remove_parent(child.id, parent.id)

        parent_updated = ops.get_task(parent.id)
        child_updated = ops.get_task(child.id)
        assert child.id not in parent_updated.children
        assert parent.id not in child_updated.depends_on

    def test_remove_parent_not_found(self) -> None:
        """存在しない親子関係を削除しようとすると OpsError が発生することを確認"""
        with pytest.raises(ops.OpsError) as exec_info:
            ops.remove_parent("child", "parent")
        assert "Task not found" in str(exec_info.value)


if __name__ == "__main__":
    unittest.main()
