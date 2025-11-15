from collections import deque
from typing import Literal

from dandori.core.models import Task
from dandori.util.time import now_iso


def task_sort_key(
    t: Task,
    *,
    order_with_no_start: Literal["now", "end_of_time"] = "now",
) -> tuple[int, str, str, str]:
    # priority 降順 → start_date(or now扱い) → created_at → id
    # startが無いものはnow扱いか、後置きしたい場合は調整(9999-12-31T23:59:59)にする
    if order_with_no_start == "now":
        start = t.start_date or now_iso()
    elif order_with_no_start == "end_of_time":
        start = "9999-12-31T23:59:59"
    return (-t.priority, start, t.created_at, t.id)


def topo_sort(tasks: dict[str, Task]) -> list[Task]:
    # Kahn法(is_archivedは無視して全体順序を返す)
    indeg = {tid: len(t.depends_on) for tid, t in tasks.items()}
    q = deque[Task]([tasks[tid] for tid, d in indeg.items() if d == 0])
    res: list[Task] = []
    seen: set[str] = set[str]()

    while q:
        t = q.popleft()
        if t.id in seen:
            continue
        seen.add(t.id)
        res.append(t)
        for c in t.children:
            indeg[c] -= 1
            if indeg[c] == 0:
                q.append(tasks[c])

    # 残り(サイクルや未接続)は後方に
    for tid, t in tasks.items():
        if tid not in seen:
            res.append(t)

    return res
