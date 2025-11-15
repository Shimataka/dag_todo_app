from dandori.core.models import Task

WHITE = 0
GRAY = 1
BLACK = 2


def detect_cycles(tasks: dict[str, Task]) -> list[list[str]]:
    """Detect all cycles in the DAG using DFS.

    Returns a list of cycles, where each cycle is represented as a list of task IDs.
    """
    cycles: list[list[str]] = []
    color: dict[str, int] = dict.fromkeys(tasks.keys(), WHITE)

    def dfs(u: str, path: list[str]) -> None:
        if color[u] == GRAY:
            # Cycle detected
            cycle_start = path.index(u)
            cycle = [*path[cycle_start:], u]
            cycles.append(cycle)
            return
        if color[u] == BLACK:
            return

        color[u] = GRAY
        path.append(u)

        t = tasks.get(u)
        if t:
            for child_id in t.children:
                if child_id in tasks:
                    dfs(child_id, path[:])  # path のコピーを渡す

        color[u] = BLACK

    for tid in tasks:
        if color[tid] == WHITE:
            dfs(tid, [])

    return cycles


def detect_inconsistencies(tasks: dict[str, Task]) -> list[tuple[str, str, str]]:
    """Detect inconsistencies in bidirectional links.

    Returns a list of (task_id, issue_type, related_id) tuples.
    issue_type can be:
    - "missing_child": task_id has depends_on[related_id] but related_id doesn't have task_id in children
    - "missing_parent": task_id has children[related_id] but related_id doesn't have task_id in depends_on
    """
    inconsistencies: list[tuple[str, str, str]] = []

    for tid, t in tasks.items():
        # Check depends_on -> children consistency
        for parent_id in t.depends_on:
            if parent_id not in tasks:
                continue
            parent_task = tasks[parent_id]
            if tid not in parent_task.children:
                inconsistencies.append((tid, "missing_child", parent_id))

        # Check children -> depends_on consistency
        for child_id in t.children:
            if child_id not in tasks:
                continue
            child_task = tasks[child_id]
            if tid not in child_task.depends_on:
                inconsistencies.append((tid, "missing_parent", child_id))

    return inconsistencies
