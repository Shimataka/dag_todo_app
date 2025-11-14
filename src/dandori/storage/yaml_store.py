from pathlib import Path

import yaml  # type: ignore[import-untyped]
from pyresults import Err, Ok, Result

from dandori.core.models import Task
from dandori.storage.base import Store
from dandori.util.time import now_iso


class StoreToYAML(Store):
    def __init__(self, data_path: str | None = None) -> None:
        super().__init__(data_path)

    # ---- 基本IO ----

    def load(self) -> None:
        _path = Path(self.data_path)
        if _path.exists():
            with _path.open(encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
                for tid, td in raw.get("tasks", {}).items():
                    self._tasks[tid] = Task.from_dict(td)
        else:
            self._tasks = {}

    def save(self) -> None:
        raw = {"tasks": {tid: t.to_dict() for tid, t in self._tasks.items()}}
        _path = Path(self.data_path)
        with _path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(raw, f, allow_unicode=True, sort_keys=True)

    # ---- タスク操作 ----

    def add_task(self, task: Task, *, id_overwritten: str | None = None) -> Result[None, str]:
        if id_overwritten is not None:
            task.id = id_overwritten
        if task.id in self._tasks:
            return Err[None, str](f"Task already exists: {task.id}")
        self._tasks[task.id] = task
        return Ok[None, str](None)

    def get(self, task_id: str) -> Result[Task, str]:
        t = self._tasks.get(task_id)
        if not t:
            _msg = f"Task not found: {task_id}"
            return Err[Task, str](_msg)
        return Ok[Task, str](t)

    def get_all_tasks(self) -> Result[dict[str, Task], str]:
        return Ok[dict[str, Task], str](self._tasks)

    def remove(self, task_id: str) -> Result[None, str]:
        match self.get(task_id):
            case Ok(t):
                for pid in t.depends_on:
                    self.unlink(pid, task_id)
                for cid in t.children:
                    self.unlink(task_id, cid)
                del self._tasks[task_id]
                return Ok[None, str](None)
            case Err(e):
                return Err[None, str](e)
            case _:
                return Err[None, str]("Unexpected error")

    def link(self, parent_id: str, child_id: str) -> Result[None, str]:
        # 循環検出
        if self._creates_cycle(parent_id, child_id):
            _msg = f"Cycle detected: {parent_id} -> {child_id}"
            return Err[None, str](_msg)
        _p = self.get(parent_id)
        _c = self.get(child_id)
        if _p.is_err() or _c.is_err():
            return Err[None, str](_p.unwrap_err() or _c.unwrap_err())
        p = _p.unwrap()
        c = _c.unwrap()
        if child_id not in p.children:
            p.children.append(child_id)
        if parent_id not in c.depends_on:
            c.depends_on.append(parent_id)
        p.updated_at = now_iso()
        c.updated_at = now_iso()
        return Ok[None, str](None)

    def unlink(self, parent_id: str, child_id: str) -> Result[None, str]:
        _p = self.get(parent_id)
        _c = self.get(child_id)
        if _p.is_err() or _c.is_err():
            return Err[None, str](_p.unwrap_err() or _c.unwrap_err())
        p = _p.unwrap()
        c = _c.unwrap()
        if child_id in p.children:
            p.children.remove(child_id)
        if parent_id in c.depends_on:
            c.depends_on.remove(parent_id)
        p.updated_at = now_iso()
        c.updated_at = now_iso()
        return Ok[None, str](None)

    # ---- アーカイブ (弱連結成分単位) ----

    def archive_component(self, task_id: str, flag: bool) -> Result[list[str], str]:  # noqa: FBT001
        comp = self._weakly_connected_component(task_id)
        if comp.is_err():
            return Err[list[str], str](comp.unwrap_err())
        comp = comp.unwrap()
        for tid in comp:
            _t = self.get(tid)
            if _t.is_err():
                return Err[list[str], str](_t.unwrap_err())
            t = _t.unwrap()
            t.is_archived = flag
            t.updated_at = now_iso()
        return Ok[list[str], str](list[str](comp))

    def _weakly_connected_component(self, start: str) -> Result[set[str], str]:
        seen: set[str] = set[str]()
        stack = [start]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            _t = self.get(cur)
            if _t.is_err():
                return Err[set[str], str](_t.unwrap_err())
            t = _t.unwrap()
            stack.extend(t.children)
            stack.extend(t.depends_on)
        return Ok[set[str], str](seen)

    # ---- 依存理由表示 (why→reason) ----

    def reason(self, task_id: str) -> Result[dict[str, list[str]], str]:
        _t = self.get(task_id)
        if _t.is_err():
            return Err[dict[str, list[str]], str](_t.unwrap_err())
        t = _t.unwrap()
        return Ok[dict[str, list[str]], str](
            {
                "task": [t.title],
                "depends_on": [self.get(pid).unwrap().title for pid in t.depends_on],
                "children": [self.get(cid).unwrap().title for cid in t.children],
            },
        )

    # ---- 挿入機能 A -> (new) -> B ----

    def insert_between(self, a: str, b: str, new_task: Task) -> Result[None, str]:
        # A->B の直接辺が無くても許容: 存在する親子関係を保ちつつ "間に入る"
        _res = self.add_task(new_task)
        if _res.is_err():
            return Err[None, str](_res.unwrap_err())

        # もしA->Bが直結していれば切ってA->new, new->B
        _a_t = self.get(a)
        _b_t = self.get(b)
        if _a_t.is_err() or _b_t.is_err():
            return Err[None, str](_a_t.unwrap_err() or _b_t.unwrap_err())
        a_t = _a_t.unwrap()
        b_t = _b_t.unwrap()
        if b in a_t.children and a in b_t.depends_on:
            _res = self.unlink(a, b)
            if _res.is_err():
                return Err[None, str](_res.unwrap_err())

        # A->new, new->B を確実に張る
        _a = self.link(a, new_task.id)
        _b = self.link(new_task.id, b)
        if _a.is_err() or _b.is_err():
            _a_res = self.unlink(a, new_task.id)
            _b_res = self.unlink(new_task.id, b)
            if _a_res.is_err() or _b_res.is_err():
                return Err[None, str](f"Failed to rollback on error: {_a_res.unwrap_err() or _b_res.unwrap_err()}")
            _res = self.remove(new_task.id)
            if _res.is_err():
                return Err[None, str](f"Failed to remove new task: {_res.unwrap_err()}")
            return Err[None, str](f"Failed to link: {_a.unwrap_err() or _b.unwrap_err() or 'Unknown error'}")
        return Ok[None, str](None)

    # ---- 循環検出 ----

    def _creates_cycle(self, parent_id: str, child_id: str) -> bool:
        seen: set[str] = set[str]()
        stack = [child_id]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            if cur == parent_id:
                return True
            _t = self.get(cur)
            if _t.is_err():
                continue
            t = _t.unwrap()
            stack.extend(t.children)
        return False
