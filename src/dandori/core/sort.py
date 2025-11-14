from dandori.core.models import Task


def task_sort_key(t: Task) -> tuple[int, str, str, str]:
    # priority 降順 → start_date(or now扱い) → created_at → id
    # startが無いものはnow扱い→後置きしたい場合は調整(9999-12-31T23:59:59)
    start = t.start_date or "9999-12-31T23:59:59"
    return (-t.priority, start, t.created_at, t.id)


def topo_sort(tasks: dict[str, Task]) -> list[Task]:
    # Kahn法(is_archivedは無視して全体順序を返す)
    indeg = {tid: len(t.depends_on) for tid, t in tasks.items()}
    q = [tasks[tid] for tid, d in indeg.items() if d == 0]
    res: list[Task] = []
    seen: set[str] = set[str]()

    while q:
        t = q.pop(0)
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
