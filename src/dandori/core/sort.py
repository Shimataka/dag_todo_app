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
    """与えられた tasks の誘導部分グラフに対するトポロジカルソート.

    tasks に含まれないノードへの edge は無視する。
    これにより、status / archived / requested_only などでフィルタした
    部分集合に対しても安全に利用できる。
    """
    # 全nodeのindegreeを0で初期化
    indeg: dict[str, int] = dict.fromkeys(tasks.keys(), 0)

    # tasksに含まれるnodeのedgeのみを数える
    for t in tasks.values():
        for child_id in t.children:
            if child_id in tasks:
                indeg[child_id] += 1

    # indegreeが0のnodeをtask_sort_keyでソートしてキューに積む
    zero_ids = [tid for tid, d in indeg.items() if d == 0]
    zero_ids.sort(key=lambda tid: task_sort_key(tasks[tid]))
    q: deque[str] = deque[str](zero_ids)
    result: list[Task] = []

    while q:
        u = q.popleft()
        result.append(tasks[u])

        # childが部分グラフ外の場合はスキップする
        for child_id in tasks[u].children:
            if child_id not in indeg:
                continue
            indeg[child_id] -= 1
            if indeg[child_id] == 0:
                q.append(child_id)

    # (念の為) 残ったnodeがあったら後方に足す
    if len(result) < len(tasks):
        in_result = {t.id for t in result}
        remains = [t for tid, t in tasks.items() if tid not in in_result]
        remains.sort(key=lambda t: task_sort_key(t))
        result.extend(remains)

    return result
