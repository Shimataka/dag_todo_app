import json
import sqlite3
from collections.abc import Callable
from typing import Any

from pyresults import Err, Ok, Result

from dandori.core.models import Task
from dandori.storage.base import Store
from dandori.util.logger import setup_logger
from dandori.util.time import now_iso

logger = setup_logger("dandori", is_stream=True, is_file=True)


class StoreToSQLite(Store):
    """SQLite3 バックエンド実装.

    - tasks テーブル: Task 本体
    - edges テーブル: parent_id -> child_id の DAG エッジ
    """

    def __init__(self, data_path: str | None = None) -> None:
        super().__init__(data_path)
        self._conn: sqlite3.Connection | None = None

    # ---- low-level helpers ---------------------------------------------

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.data_path)
            self._conn.row_factory = sqlite3.Row
            # 外部キー制約と ON DELETE CASCADE を有効化
            self._conn.execute("PRAGMA foreign_keys = ON")
        return self._conn

    def _init_schema(self) -> None:
        """テーブルがなければ作成する."""
        c = self.conn
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                owner TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                done_at TEXT,
                due_date TEXT,
                start_at TEXT,
                priority INTEGER,
                status TEXT NOT NULL,
                is_archived INTEGER NOT NULL DEFAULT 0,
                assigned_to TEXT,
                requested_by TEXT,
                requested_at TEXT,
                requested_note TEXT,
                tags TEXT,
                metadata TEXT
            )
            """,
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS edges (
                parent_id TEXT NOT NULL,
                child_id  TEXT NOT NULL,
                PRIMARY KEY (parent_id, child_id),
                FOREIGN KEY (parent_id) REFERENCES tasks(id) ON DELETE CASCADE,
                FOREIGN KEY (child_id)  REFERENCES tasks(id) ON DELETE CASCADE
            )
            """,
        )
        c.commit()

    @staticmethod
    def _decode_tags(raw: str | None) -> list[str]:
        if not raw:
            return []
        try:
            v = json.loads(raw)
            if isinstance(v, list):
                return [str(x) for x in v]
        except Exception:
            # 壊れていても致命的ではないので空にしておく
            logger.exception("Failed to decode tags JSON; fallback to [].")
        return []

    @staticmethod
    def _encode_tags(tags: list[str]) -> str:
        return json.dumps(tags, ensure_ascii=False)

    @staticmethod
    def _decode_metadata(raw: str | None) -> dict[str, Any]:
        if not raw:
            return {}
        try:
            v = json.loads(raw)
            if isinstance(v, dict):
                return v
        except Exception:
            logger.exception("Failed to decode metadata JSON; fallback to {}.")
        return {}

    @staticmethod
    def _encode_metadata(md: dict[str, Any]) -> str:
        try:
            return json.dumps(md, ensure_ascii=False)
        except Exception:
            logger.exception("Failed to encode metadata JSON; fallback to '{}'.")
            return "{}"

    def _row_to_task(self, row: sqlite3.Row) -> Task:
        return Task(
            id=row["id"],
            owner=row["owner"],
            title=row["title"],
            description=row["description"] or "",
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            done_at=row["done_at"],
            due_date=row["due_date"],
            start_at=row["start_at"],
            priority=row["priority"],
            status=row["status"],
            depends_on=[],  # edges から埋める
            children=[],  # edges から埋める
            is_archived=bool(row["is_archived"]),
            assigned_to=row["assigned_to"],
            requested_by=row["requested_by"],
            requested_at=row["requested_at"],
            requested_note=row["requested_note"],
            tags=self._decode_tags(row["tags"]),
            metadata=self._decode_metadata(row["metadata"]),
        )

    def _load_all_tasks_dict(self) -> dict[str, Task]:
        """Tasks + edges から Task 辞書を構築."""
        c = self.conn
        tasks: dict[str, Task] = {}
        for row in c.execute("SELECT * FROM tasks"):
            t = self._row_to_task(row)
            tasks[t.id] = t

        for row in c.execute("SELECT parent_id, child_id FROM edges"):
            pid = row["parent_id"]
            cid = row["child_id"]
            parent = tasks.get(pid)
            child = tasks.get(cid)
            if parent is None or child is None:
                continue
            if cid not in parent.children:
                parent.children.append(cid)
            if pid not in child.depends_on:
                child.depends_on.append(pid)
        return tasks

    # ---- 基本IO ---------------------------------------------------------

    def load(self) -> None:
        """SQLite の接続とスキーマを初期化.

        YAML 実装と違い、ここでは DB をメモリに持たず、必要なときにクエリする。
        """
        self._init_schema()

    def save(self) -> None:
        """SQLite では commit 相当."""
        try:
            self.conn.commit()
        except Exception as e:
            msg = f"Error on save(): {e!s}"
            logger.exception(msg)

    # ---- データ操作 -----------------------------------------------------

    def commit(self) -> None:
        try:
            self.conn.commit()
        except Exception as e:
            msg = f"Error on commit(): {e!s}"
            logger.exception(msg)

    def rollback(self) -> None:
        try:
            self.conn.rollback()
        except Exception as e:
            msg = f"Error on rollback(): {e!s}"
            logger.exception(msg)

    # ---- データ取得 -----------------------------------------------------

    def get_task(self, task_id: str) -> Result[Task, str]:
        c = self.conn
        cur = c.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = cur.fetchone()
        if row is None:
            msg = f"Task not found: {task_id}"
            logger.exception(msg)
            return Err(msg)

        # まず単体の Task を作る
        t = self._row_to_task(row)

        # 親子関係を SQL から埋める
        deps: list[str] = [
            r["parent_id"] for r in c.execute("SELECT parent_id FROM edges WHERE child_id = ?", (task_id,))
        ]
        children: list[str] = [
            r["child_id"] for r in c.execute("SELECT child_id FROM edges WHERE parent_id = ?", (task_id,))
        ]
        t.depends_on = deps
        t.children = children
        return Ok(t)

    def get_tasks(self, task_ids: list[str]) -> Result[list[Task], str]:
        # YAML 実装に合わせて「存在しない ID は単に無視し、Err は返さない」
        if not task_ids:
            return Ok([])
        tasks: list[Task] = []
        for tid in task_ids:
            match self.get_task(tid):
                case Ok(t):
                    tasks.append(t)
                case Err(e):
                    logger.exception("get_tasks: %s", e)
                    continue
        return Ok(tasks)

    def get_all_tasks(self) -> Result[dict[str, Task], str]:
        try:
            tasks = self._load_all_tasks_dict()
            return Ok(tasks)
        except Exception as e:
            msg = f"Error (get_all_tasks): {e!s}"
            logger.exception(msg)
            return Err(msg)

    # ---- タスク操作 -----------------------------------------------------

    def add_task(self, task: Task, *, id_overwritten: str | None = None) -> Result[None, str]:
        if id_overwritten is not None:
            task.id = id_overwritten

        c = self.conn
        try:
            cur = c.execute("SELECT 1 FROM tasks WHERE id = ?", (task.id,))
            if cur.fetchone() is not None:
                msg = f"Task already exists: {task.id}"
                logger.exception(msg)
                return Err(msg)

            c.execute(
                """
                INSERT INTO tasks (
                    id, owner, title, description,
                    created_at, updated_at, done_at,
                    due_date, start_at, priority,
                    status, is_archived,
                    assigned_to, requested_by, requested_at, requested_note,
                    tags, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.id,
                    task.owner,
                    task.title,
                    task.description,
                    task.created_at,
                    task.updated_at,
                    task.done_at,
                    task.due_date,
                    task.start_at,
                    task.priority,
                    task.status,
                    int(task.is_archived),
                    task.assigned_to,
                    task.requested_by,
                    task.requested_at,
                    task.requested_note,
                    self._encode_tags(task.tags),
                    self._encode_metadata(task.metadata),
                ),
            )
            return Ok(None)
        except Exception as e:
            msg = f"Error (add_task): {e!s}"
            logger.exception(msg)
            return Err(msg)

    def update_task(self, task: Task) -> Result[None, str]:
        c = self.conn
        cur = c.execute("SELECT 1 FROM tasks WHERE id = ?", (task.id,))
        if cur.fetchone() is None:
            msg = f"Task not found: {task.id}"
            logger.exception(msg)
            return Err(msg)
        try:
            c.execute(
                """
                UPDATE tasks SET
                    owner = ?,
                    title = ?,
                    description = ?,
                    updated_at = ?,
                    done_at = ?,
                    due_date = ?,
                    start_at = ?,
                    priority = ?,
                    status = ?,
                    is_archived = ?,
                    assigned_to = ?,
                    requested_by = ?,
                    requested_at = ?,
                    requested_note = ?,
                    tags = ?,
                    metadata = ?
                WHERE id = ?
                """,
                (
                    task.owner,
                    task.title,
                    task.description,
                    task.updated_at,
                    task.done_at,
                    task.due_date,
                    task.start_at,
                    task.priority,
                    task.status,
                    int(task.is_archived),
                    task.assigned_to,
                    task.requested_by,
                    task.requested_at,
                    task.requested_note,
                    self._encode_tags(task.tags),
                    self._encode_metadata(task.metadata),
                    task.id,
                ),
            )
            # StoreToSQLite では save() 時に commit する方針ならここでは commit しない。
            return Ok(None)
        except Exception as e:
            msg = f"Error (update_task): {e!s}"
            logger.exception(msg)
            return Err(msg)

    def remove_task(self, task_id: str) -> Result[None, str]:
        c = self.conn
        try:
            # 存在確認
            match self.get_task(task_id):
                case Err(e):
                    msg = f"Error (remove_task): {e}"
                    logger.exception(msg)
                    return Err(msg)
                case Ok(_):
                    pass

            # edges は ON DELETE CASCADE でもよいが、明示的に削除しておく
            c.execute("DELETE FROM edges WHERE parent_id = ? OR child_id = ?", (task_id, task_id))
            c.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            return Ok(None)
        except Exception as e:
            msg = f"Error (remove_task): {e!s}"
            logger.exception(msg)
            return Err(msg)

    def link_tasks(self, parent_id: str, child_id: str) -> Result[None, str]:
        """parent_id -> child_id のエッジを追加 (循環検出付き)."""
        # 循環検出
        match self._has_task_cycle(parent_id, child_id):
            case Ok(True):
                msg = f"Cycle detected: {parent_id} -> {child_id}"
                logger.exception(msg)
                return Err(msg)
            case Ok(False):
                pass
            case Err(e):
                msg = f"Error (link_tasks/cycle): {e}"
                logger.exception(msg)
                return Err(msg)
            case _:
                msg = "Unexpected error (link_tasks/cycle)"
                logger.exception(msg)
                return Err(msg)

        c = self.conn
        try:
            # タスク存在確認
            match (self.get_task(parent_id), self.get_task(child_id)):
                case (Err(e), _) | (_, Err(e)):
                    msg = f"Error (link_tasks/get): {e}"
                    logger.exception(msg)
                    return Err(msg)
                case (Ok(_), Ok(_)):
                    pass

            # 既にあれば何もしない
            cur = c.execute(
                "SELECT 1 FROM edges WHERE parent_id = ? AND child_id = ?",
                (parent_id, child_id),
            )
            if cur.fetchone() is None:
                c.execute(
                    "INSERT INTO edges (parent_id, child_id) VALUES (?, ?)",
                    (parent_id, child_id),
                )
                now = now_iso()
                c.execute(
                    "UPDATE tasks SET updated_at = ? WHERE id IN (?, ?)",
                    (now, parent_id, child_id),
                )
            return Ok(None)
        except Exception as e:
            msg = f"Error (link_tasks): {e!s}"
            logger.exception(msg)
            return Err(msg)

    def unlink_tasks(self, parent_id: str, child_id: str) -> Result[None, str]:
        c = self.conn
        try:
            match (self.get_task(parent_id), self.get_task(child_id)):
                case (Err(e), _) | (_, Err(e)):
                    msg = f"Error (unlink_tasks/get): {e}"
                    logger.exception(msg)
                    return Err(msg)
                case (Ok(_), Ok(_)):
                    pass

            cur = c.execute(
                "SELECT 1 FROM edges WHERE parent_id = ? AND child_id = ?",
                (parent_id, child_id),
            )
            if cur.fetchone() is None:
                # もともとリンクが無ければ何もしない
                return Ok(None)
            c.execute(
                "DELETE FROM edges WHERE parent_id = ? AND child_id = ?",
                (parent_id, child_id),
            )
            now = now_iso()
            c.execute(
                "UPDATE tasks SET updated_at = ? WHERE id IN (?, ?)",
                (now, parent_id, child_id),
            )
            return Ok(None)
        except Exception as e:
            msg = f"Error (unlink_tasks): {e!s}"
            logger.exception(msg)
            return Err(msg)

    # ---- アーカイブ / 弱連結成分 ----------------------------------------

    def weakly_connected_component(self, start: str) -> Result[list[Task], str]:
        try:
            # start が存在するか先にチェック
            match self.get_task(start):
                case Err(e):
                    msg = f"Error (weakly_connected_component/get): {e}"
                    logger.exception(msg)
                    return Err(msg)
                case Ok(_):
                    pass

            c = self.conn
            seen: set[str] = set()
            stack: list[str] = [start]
            while stack:
                cur = stack.pop()
                if cur in seen:
                    continue
                seen.add(cur)
                # out
                stack.extend(
                    r["child_id"] for r in c.execute("SELECT child_id FROM edges WHERE parent_id = ?", (cur,))
                )
                # in
                stack.extend(
                    r["parent_id"] for r in c.execute("SELECT parent_id FROM edges WHERE child_id = ?", (cur,))
                )

            tasks: list[Task] = []
            for tid in seen:
                match self.get_task(tid):
                    case Ok(t):
                        tasks.append(t)
                    case Err(e):
                        msg = f"Error (weakly_connected_component/get_task): {e}"
                        logger.exception(msg)
                        return Err(msg)
            return Ok(tasks)
        except Exception as e:
            msg = f"Error (weakly_connected_component): {e!s}"
            logger.exception(msg)
            return Err(msg)

    def archive_tasks(self, task_id: str) -> Result[list[str], str]:
        match self.weakly_connected_component(task_id):
            case Err(e):
                msg = f"Error (archive_tasks/component): {e}"
                logger.exception(msg)
                return Err(msg)
            case Ok(comp):
                ids = [t.id for t in comp]
                if not ids:
                    return Ok([])
                placeholders = ",".join("?" for _ in ids)
                now = now_iso()
                try:
                    self.conn.execute(
                        f"UPDATE tasks SET is_archived = 1, updated_at = ? WHERE id IN ({placeholders})",  # noqa: S608
                        (now, *ids),
                    )
                    return Ok(ids)
                except Exception as e:
                    msg = f"Error (archive_tasks): {e!s}"
                    logger.exception(msg)
                    return Err(msg)
            case _:
                msg = "Unexpected error (archive_tasks/component)"
                logger.exception(msg)
                return Err(msg)

    def unarchive_tasks(self, task_id: str) -> Result[list[str], str]:
        match self.weakly_connected_component(task_id):
            case Err(e):
                msg = f"Error (unarchive_tasks/component): {e}"
                logger.exception(msg)
                return Err(msg)
            case Ok(comp):
                ids = [t.id for t in comp]
                if not ids:
                    return Ok([])
                placeholders = ",".join("?" for _ in ids)
                now = now_iso()
                try:
                    self.conn.execute(
                        f"UPDATE tasks SET is_archived = 0, updated_at = ? WHERE id IN ({placeholders})",  # noqa: S608
                        (now, *ids),
                    )
                    return Ok(ids)
                except Exception as e:
                    msg = f"Error (unarchive_tasks): {e!s}"
                    logger.exception(msg)
                    return Err(msg)
            case _:
                msg = "Unexpected error (unarchive_tasks/component)"
                logger.exception(msg)
                return Err(msg)

    # ---- 依存関係情報 ---------------------------------------------------

    def get_dependency_info(self, task_id: str) -> Result[dict[str, list[str]], str]:
        match self.get_task(task_id):
            case Err(e):
                msg = f"Error (get_dependency_info/get_task): {e}"
                logger.exception(msg)
                return Err(msg)
            case Ok(t):
                deps: list[str] = []
                for pid in t.depends_on:
                    match self.get_task(pid):
                        case Ok(pt):
                            deps.append(pt.title)
                        case Err(_):
                            deps.append(f"<{pid} not found>")

                children: list[str] = []
                for cid in t.children:
                    match self.get_task(cid):
                        case Ok(ct):
                            children.append(ct.title)
                        case Err(_):
                            children.append(f"<{cid} not found>")

                return Ok({"task": [t.title], "depends_on": deps, "children": children})
            case _:
                msg = "Unexpected error (get_dependency_info/get_task)"
                logger.exception(msg)
                return Err(msg)

    # ---- 挿入機能 A -> (new) -> B --------------------------------------

    def insert_task(
        self,
        a: str,
        b: str,
        new_task: Task,
        *,
        id_overwritten: str | None = None,
    ) -> Result[None, str]:
        """既存のエッジ A->B の間に new_task を挿入 (YAML 実装と同等)."""
        match (
            self._add_inserted_task(new_task, id_overwritten=id_overwritten)
            .and_then(lambda _: self._remove_existing_edge(a, b))
            .and_then(lambda _: self._link_inserted_task(a, b, new_task))
        ):
            case Ok(None):
                return Ok(None)
            case Err(e):
                msg = f"Error (insert_task): {e}"
                logger.exception(msg)
                return Err(msg)
            case _:
                msg = "Unexpected error (insert_task)"
                logger.exception(msg)
                return Err(msg)

    def _add_inserted_task(
        self,
        new_task: Task,
        *,
        id_overwritten: str | None = None,
    ) -> Result[None, str]:
        # A->B の直接辺が無くても許容: 既存の親子関係は保ちつつ new を追加
        return self.add_task(new_task, id_overwritten=id_overwritten)

    def _remove_existing_edge(self, a: str, b: str) -> Result[None, str]:
        match (self.get_task(a), self.get_task(b)):
            case (Err(e), _) | (_, Err(e)):
                msg = f"Error (remove_existing_edge/get): {e}"
                logger.exception(msg)
                return Err(msg)
            case (Ok(at), Ok(bt)):
                if b in at.children and a in bt.depends_on:
                    return self.unlink_tasks(a, b)
                return Ok(None)
            case _:
                msg = "Unexpected error (remove_existing_edge/get)"
                logger.exception(msg)
                return Err(msg)

    def _link_inserted_task(self, a: str, b: str, new_task: Task) -> Result[None, str]:
        match (self.link_tasks(a, new_task.id), self.link_tasks(new_task.id, b)):
            case (Ok(None), Ok(None)):
                return Ok(None)
            case (Err(e), Ok(None)):
                return self._rollback_on_error(
                    e,
                    lambda: self.unlink_tasks(new_task.id, b).and_then(
                        lambda _: self.remove_task(new_task.id),
                    ),
                )
            case (Ok(None), Err(e)):
                return self._rollback_on_error(
                    e,
                    lambda: self.unlink_tasks(a, new_task.id).and_then(
                        lambda _: self.remove_task(new_task.id),
                    ),
                )
            case (Err(e1), Err(e2)):
                msg = f"Failed to link to parent: {e1}, and failed to link to child: {e2}"
                logger.exception(msg)
                return Err(msg)
            case _:
                msg = "Unexpected error (_link_inserted_task)"
                logger.exception(msg)
                return Err(msg)

    def _rollback_on_error(
        self,
        error_message: str,
        rollback_fn: Callable[[], Result[None, str]],
    ) -> Result[None, str]:
        match rollback_fn():
            case Ok(None):
                logger.error(error_message)
                return Err(error_message)
            case Err(ee):
                msg = f"{error_message} (and rollback failed: {ee})"
                logger.error(msg)
                return Err(msg)
            case _:
                msg = f"{error_message} (and rollback failed: Unexpected error)"
                logger.error(msg)
                return Err(msg)

    # ---- 循環検出 -------------------------------------------------------

    def _has_task_cycle(self, parent_id: str, child_id: str) -> Result[bool, str]:
        """child_id から子方向に辿って parent_id に到達するかどうかを調べる."""
        try:
            # child_id の存在チェック
            match self.get_task(child_id):
                case Err(e):
                    msg = f"Error (_has_task_cycle/get_child): {e}"
                    logger.exception(msg)
                    return Err(msg)
                case Ok(_):
                    pass

            seen: set[str] = set()
            stack: list[str] = [child_id]
            while stack:
                cur = stack.pop()
                if cur in seen:
                    continue
                seen.add(cur)
                if cur == parent_id:
                    return Ok(value=True)
                stack.extend(
                    r["child_id"] for r in self.conn.execute("SELECT child_id FROM edges WHERE parent_id = ?", (cur,))
                )
            return Ok(value=False)
        except Exception as e:
            msg = f"Error (_has_task_cycle): {e!s}"
            logger.exception(msg)
            return Err(msg)
