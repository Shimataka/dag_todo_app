import copy
from collections.abc import Callable
from pathlib import Path

import yaml  # type: ignore[import-untyped]
from pyresults import Err, Ok, Result

from dandori.core.models import Task
from dandori.storage.base import Store
from dandori.util.logger import setup_logger
from dandori.util.time import now_iso

logger = setup_logger("dandori", is_stream=True, is_file=True)


class StoreToYAML(Store):
    def __init__(self, data_path: str | None = None) -> None:
        super().__init__(data_path)
        self._tasks: dict[str, Task] = {}
        self._tmp_tasks: dict[str, Task] = {}

    # ---- 基本IO ----

    def load(self) -> None:
        _path = Path(self.data_path)
        _tasks: dict[str, Task] = {}
        if _path.exists():
            with _path.open(encoding="utf-8") as f:
                try:
                    raw = yaml.safe_load(f) or {}
                except yaml.YAMLError as e:
                    _msg = f"Failed to load YAML file: {e}"
                    logger.exception(_msg)
                    # Initialize empty tasks if error occurs
                    self._tasks = {}
                    self._tmp_tasks = {}
                    return
                for tid, td in raw.get("tasks", {}).items():
                    _tasks[tid] = Task.from_dict(td)
        else:
            _tasks = {}

        # treat read content as commited state, and copy the tasks to the internal state
        self._tasks = copy.deepcopy(_tasks)
        self._tmp_tasks = copy.deepcopy(_tasks)

    def save(self) -> None:
        # save the internal state (tasks) to the file
        raw = {"tasks": {tid: t.to_dict() for tid, t in self.tasks.items()}}
        _path = Path(self.data_path)
        with _path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(raw, f, allow_unicode=True, sort_keys=True)

    # ---- データ操作 ----

    @property
    def tasks(self) -> dict[str, Task]:
        return self._tmp_tasks

    @tasks.setter
    def tasks(self, value: dict[str, Task]) -> None:
        self._tmp_tasks = value

    def commit(self) -> None:
        """変更を永続化する。

        内部の_tasks辞書の内容を永続化します。
        """
        self._tasks = copy.deepcopy(self._tmp_tasks)

    def rollback(self) -> None:
        """変更を破棄する。

        内部の_tasks辞書の内容を破棄します。
        """
        self._tmp_tasks = copy.deepcopy(self._tasks)

    # ---- データ取得 ----

    def get_task(self, task_id: str) -> Result[Task, str]:
        """タスクIDでタスクを取得する。

        Args:
            task_id: 取得するタスクのID

        Returns:
            Ok(Task): 成功時
            Err(str): 失敗時（例: タスクが見つからない）
        """
        t = self.tasks.get(task_id)
        if t is None:
            _msg = f"Task not found: {task_id}"
            logger.exception(_msg)
            return Err[Task, str](_msg)
        return Ok[Task, str](t)

    def get_tasks(self, task_ids: list[str]) -> Result[list[Task], str]:
        """タスクIDのリストでタスクを取得する。

        Args:
            task_ids: 取得するタスクのIDのリスト

        Returns:
            Ok(list[Task]): 成功時（タスクのリスト）
            Err(str): 失敗時
        """
        return Ok[list[Task], str]([self.tasks[tid] for tid in task_ids if tid in self.tasks])

    def get_all_tasks(self) -> Result[dict[str, Task], str]:
        """全タスクを取得する。

        Returns:
            Ok(dict[str, Task]): 成功時（タスクIDをキーとする辞書）
            Err(str): 失敗時
        """
        return Ok[dict[str, Task], str](self.tasks)

    # ---- タスク操作 ----

    def add_task(self, task: Task, *, id_overwritten: str | None = None) -> Result[None, str]:
        """タスクを追加する。

        Args:
            task: 追加するタスク
            id_overwritten: タスクIDを上書きする場合に指定

        Returns:
            Ok(None): 成功時
            Err(str): 失敗時（例: 既に存在するID）
        """
        if id_overwritten is not None:
            task.id = id_overwritten
        match self.get_all_tasks():
            case Ok(tasks):
                if task.id in tasks:
                    _msg = f"Task already exists: {task.id}"
                    logger.exception(_msg)
                    return Err[None, str](_msg)
                self.tasks[task.id] = task
                return Ok[None, str](None)
            case _:
                _msg = "Unexpected error"
                logger.exception(_msg)
                return Err[None, str](_msg)

    def remove_task(self, task_id: str) -> Result[None, str]:
        """タスクを削除する。

        タスクを削除する際、関連する依存関係（親子リンク）も自動的に削除されます。

        Args:
            task_id: 削除するタスクのID

        Returns:
            Ok(None): 成功時
            Err(str): 失敗時（例: タスクが見つからない）
        """
        match self.get_task(task_id):
            case Ok(t):
                for pid in t.depends_on[:]:
                    if (res := self.unlink_tasks(pid, task_id)).is_err():
                        return res
                for cid in t.children[:]:
                    if (res := self.unlink_tasks(task_id, cid)).is_err():
                        return res
                del self.tasks[task_id]
                return Ok[None, str](None)
            case Err(e):
                _msg = f"Error (remove): {e}"
                logger.exception(_msg)
                return Err[None, str](_msg)
            case _:
                _msg = "Unexpected error"
                logger.exception(_msg)
                return Err[None, str](_msg)

    def link_tasks(self, parent_id: str, child_id: str) -> Result[None, str]:
        """タスク間の依存関係を追加する（parent -> child）。

        循環が検出された場合はエラーを返します。
        parent_id から child_id への依存関係がすでに存在する場合は変更せず `Ok(None)` を返します。

        Args:
            parent_id: 親タスクのID
            child_id: 子タスクのID

        Returns:
            Ok(None): 成功時
            Err(str): 失敗時（例: 循環検出、タスクが見つからない）
        """
        # 循環検出
        match self._has_task_cycle(parent_id, child_id):
            case Ok(True):
                _msg = f"Cycle detected: {parent_id} -> {child_id}"
                logger.exception(_msg)
                return Err[None, str](_msg)
            case Ok(False):
                pass
            case Err(e):
                _msg = f"Error (link): {e}"
                logger.exception(_msg)
                return Err[None, str](_msg)
            case _:
                _msg = "Unexpected error"
                logger.exception(_msg)
                return Err[None, str](_msg)
        match (self.get_task(parent_id), self.get_task(child_id)):
            case (Ok(p), Ok(c)):
                if child_id not in p.children and parent_id not in c.depends_on:
                    p.children.append(child_id)
                    c.depends_on.append(parent_id)
                    p.updated_at = now_iso()
                    c.updated_at = now_iso()
                return Ok[None, str](None)
            case (Err(e), _) | (_, Err(e)):
                _msg = f"Error (unlink): {e}"
                logger.exception(_msg)
                return Err[None, str](_msg)
            case _:
                _msg = "Unexpected error"
                logger.exception(_msg)
                return Err[None, str](_msg)

    def unlink_tasks(self, parent_id: str, child_id: str) -> Result[None, str]:
        """タスク間の依存関係を削除する。

        parent_id から child_id への依存関係がすでに存在しない場合は変更せず `Ok(None)` を返します。

        Args:
            parent_id: 親タスクのID
            child_id: 子タスクのID

        Returns:
            Ok(None): 成功時
            Err(str): 失敗時（例: タスクが見つからない）
        """
        match (self.get_task(parent_id), self.get_task(child_id)):
            case (Ok(p), Ok(c)):
                if child_id in p.children and parent_id in c.depends_on:
                    p.children.remove(child_id)
                    c.depends_on.remove(parent_id)
                    p.updated_at = now_iso()
                    c.updated_at = now_iso()
                return Ok[None, str](None)
            case (Err(e), _) | (_, Err(e)):
                _msg = f"Error (unlink): {e}"
                logger.exception(_msg)
                return Err[None, str](_msg)
            case _:
                _msg = "Unexpected error"
                logger.exception(_msg)
                return Err[None, str](_msg)

    # ---- アーカイブ (弱連結成分単位) ----

    def archive_tasks(self, task_id: str) -> Result[list[str], str]:
        """弱連結成分単位でアーカイブ状態にする。

        指定されたタスクを含む弱連結成分（無向グラフとしての連結成分）の
        全タスクのis_archivedフラグを一括アーカイブします。

        Args:
            task_id: 起点となるタスクのID

        Returns:
            Ok(list[str]): 成功時（更新されたタスクIDのリスト）
            Err(str): 失敗時（例: タスクが見つからない）
        """
        match self.weakly_connected_component(task_id):
            case Ok(comp):
                for t in comp:
                    t.is_archived = True
                    t.updated_at = now_iso()
                return Ok[list[str], str]([t.id for t in comp])
            case Err(e):
                _msg = f"Error (archive): {e}"
                logger.exception(_msg)
                return Err[list[str], str](_msg)
            case _:
                _msg = "Unexpected error"
                logger.exception(_msg)
                return Err[list[str], str](_msg)

    def unarchive_tasks(self, task_id: str) -> Result[list[str], str]:
        """弱連結成分単位でアーカイブ状態を復元する。

        指定されたタスクを含む弱連結成分（無向グラフとしての連結成分）の
        全タスクのis_archivedフラグを一括復元します。

        Args:
            task_id: 起点となるタスクのID

        Returns:
            Ok(list[str]): 成功時（更新されたタスクIDのリスト）
            Err(str): 失敗時（例: タスクが見つからない）
        """
        match self.weakly_connected_component(task_id):
            case Ok(comp):
                for t in comp:
                    t.is_archived = False
                    t.updated_at = now_iso()
                return Ok[list[str], str]([t.id for t in comp])
            case Err(e):
                _msg = f"Error (unarchive): {e}"
                logger.exception(_msg)
                return Err[list[str], str](_msg)
            case _:
                _msg = "Unexpected error"
                logger.exception(_msg)
                return Err[list[str], str](_msg)

    def weakly_connected_component(self, start: str) -> Result[list[Task], str]:
        visited_tasks: list[Task] = []

        seen: set[str] = set[str]()
        stack: list[str] = [start]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            match self.get_task(cur):
                case Ok(t):
                    visited_tasks.append(t)
                    stack.extend(t.children)
                    stack.extend(t.depends_on)
                case Err(e):
                    _msg = f"Error (weakly_connected_component): {e}"
                    logger.exception(_msg)
                    return Err[list[Task], str](_msg)
                case _:
                    _msg = "Unexpected error"
                    logger.exception(_msg)
                    return Err[list[Task], str](_msg)
        return Ok[list[Task], str](visited_tasks)

    # ---- 依存関係情報表示 ----

    def get_dependency_info(self, task_id: str) -> Result[dict[str, list[str]], str]:
        """タスクの依存関係情報を取得する。

        Args:
            task_id: 対象タスクのID

        Returns:
            Ok(dict): 成功時（{"task": [...], "depends_on": [...], "children": [...]}）
            Err(str): 失敗時（例: タスクが見つからない）
        """
        match self.get_task(task_id):
            case Ok(t):
                deps = [
                    self.get_task(pid).map_or(lambda task: task.title, f"<{pid} not found>") for pid in t.depends_on
                ]
                chil = [self.get_task(cid).map_or(lambda task: task.title, f"<{cid} not found>") for cid in t.children]
                return Ok[dict[str, list[str]], str]({"task": [t.title], "depends_on": deps, "children": chil})
            case Err(e):
                _msg = f"Error (get_dependency_info): {e}"
                logger.exception(_msg)
                return Err[dict[str, list[str]], str](_msg)
            case _:
                _msg = "Unexpected error"
                logger.exception(_msg)
                return Err[dict[str, list[str]], str](_msg)

    # ---- 挿入機能 A -> (new) -> B ----

    def insert_task(
        self,
        a: str,
        b: str,
        new_task: Task,
        *,
        id_overwritten: str | None = None,
    ) -> Result[None, str]:
        """既存のエッジA->Bの間に新しいタスクを挿入する。

        既存のエッジA->Bが存在する場合は削除し、A->new_task->Bの構造に変更します。
        エッジが存在しない場合でも、A->new_task->Bのリンクを作成します。

        Args:
            a: 親タスクのID
            b: 子タスクのID
            new_task: 挿入する新しいタスク
            id_overwritten: 新しいタスクのIDを上書きする場合に指定

        Returns:
            Ok(None): 成功時
            Err(str): 失敗時（例: 循環検出、タスクが見つからない）
        """
        match (
            self._add_inserted_task(new_task, id_overwritten=id_overwritten)
            .and_then(lambda _: self._remove_existing_edge(a, b))
            .and_then(lambda _: self._link_inserted_task(a, b, new_task))
        ):
            case Ok(None):
                return Ok[None, str](None)
            case Err(e):
                _msg = f"Error (insert_task): {e}"
                logger.exception(_msg)
                return Err[None, str](_msg)
            case _:
                _msg = "Unexpected error"
                logger.exception(_msg)
                return Err[None, str](_msg)

    def _add_inserted_task(
        self,
        new_task: Task,
        *,
        id_overwritten: str | None = None,
    ) -> Result[None, str]:
        # A->B の直接辺が無くても許容: 存在する親子関係を保ちつつ "間に入る"
        return self.add_task(new_task, id_overwritten=id_overwritten)

    def _remove_existing_edge(self, a: str, b: str) -> Result[None, str]:
        # もしA->Bが直結していれば切ってA->new, new->B
        match (self.get_task(a), self.get_task(b)):
            case (Ok(a_t), Ok(b_t)):
                if b in a_t.children and a in b_t.depends_on:
                    return self.unlink_tasks(a, b)
                return Ok[None, str](None)
            case (Err(e), _) | (_, Err(e)):
                _msg = f"Error (remove_existing_edge): {e}"
                logger.exception(_msg)
                return Err[None, str](_msg)
            case _:
                _msg = "Unexpected error"
                logger.exception(_msg)
                return Err[None, str](_msg)

    def _link_inserted_task(self, a: str, b: str, new_task: Task) -> Result[None, str]:
        # A->new, new->B を確実に張る
        match (self.link_tasks(a, new_task.id), self.link_tasks(new_task.id, b)):
            case Ok(None), Ok(None):
                return Ok[None, str](None)
            case (Err(e), Ok(None)):
                return self._rollback_on_error(
                    e,
                    lambda: self.unlink_tasks(
                        new_task.id,
                        b,
                    ).and_then(
                        lambda _: self.remove_task(new_task.id),
                    ),
                )
            case (Ok(None), Err(e)):
                return self._rollback_on_error(
                    e,
                    lambda: self.unlink_tasks(
                        a,
                        new_task.id,
                    ).and_then(
                        lambda _: self.remove_task(new_task.id),
                    ),
                )
            case (Err(e1), Err(e2)):
                _msg = f"Failed to link to parent: {e1}, and failed to link to child: {e2}"
                logger.exception(_msg)
                return Err[None, str](_msg)
            case _:
                _msg = "Unexpected error"
                logger.exception(_msg)
                return Err[None, str](_msg)

    def _rollback_on_error(
        self,
        error_message: str,
        rollback_fn: Callable[[], Result[None, str]],
    ) -> Result[None, str]:
        """Rollback on error.

        Args:
            error_message: The error message.
            rollback_fn: The rollback function.

        Returns:
            Ok(None): Success.
            Err(str): Error.
        """
        match rollback_fn():
            case Ok(None):
                logger.error(error_message)
                return Err[None, str](error_message)
            case Err(ee):
                _msg = f"{error_message} (and rollback failed: {ee})"
                logger.error(_msg)
                return Err[None, str](_msg)
            case _:
                _msg = f"{error_message} (and rollback failed: Unexpected error)"
                logger.error(_msg)
                return Err[None, str](_msg)

    # ---- 循環検出 ----

    def _has_task_cycle(self, parent_id: str, child_id: str) -> Result[bool, str]:
        seen: set[str] = set[str]()
        stack = [child_id]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            if cur == parent_id:
                return Ok[bool, str](value=True)
            match self.get_task(cur):
                case Ok(t):
                    stack.extend(t.children)
                case Err(e):
                    _msg = f"Error (has_task_cycle): {e}"
                    logger.exception(_msg)
                    return Err[bool, str](_msg)
                case _:
                    _msg = "Unexpected error"
                    logger.exception(_msg)
                    return Err[bool, str](_msg)
        return Ok[bool, str](value=False)
