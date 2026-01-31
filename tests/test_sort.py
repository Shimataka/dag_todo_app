import unittest

from dandori.core.models import Task
from dandori.core.sort import task_sort_key, topo_sort


def _task(
    tid: str,
    start_at: str | None = None,
    created_at: str = "2024-01-01T00:00:00",
    priority: int | None = None,
    children: list[str] | None = None,
) -> Task:
    return Task(
        id=tid,
        owner="u",
        title=tid,
        start_at=start_at,
        created_at=created_at,
        priority=priority,
        children=children or [],
    )


class TestTaskSortKey(unittest.TestCase):
    def test_order_now_uses_now_iso_when_start_at_none(self) -> None:
        t = _task("a", start_at=None)
        key = task_sort_key(t, order_with_no_start="now")
        assert key[1] != "9999-12-31T23:59:59"
        assert len(key[1]) == 19  # ISO format length

    def test_order_end_of_time(self) -> None:
        t = _task("a", start_at=None)
        key = task_sort_key(t, order_with_no_start="end_of_time")
        assert key[1] == "9999-12-31T23:59:59"


class TestTopoSort(unittest.TestCase):
    def test_simple_dag(self) -> None:
        tasks = {
            "a": _task("a", children=["b"]),
            "b": _task("b", children=["c"]),
            "c": _task("c"),
        }
        result = topo_sort(tasks)
        ids = [t.id for t in result]
        assert ids.index("a") < ids.index("b") < ids.index("c")

    def test_partial_graph_skips_external_children(self) -> None:
        tasks = {
            "a": _task("a", children=["b", "x"]),
            "b": _task("b"),
        }
        result = topo_sort(tasks)
        assert len(result) == 2
        ids = [t.id for t in result]
        assert ids.index("a") < ids.index("b")

    def test_remaining_nodes_appended(self) -> None:
        # Cycle: a->b->a. Indegrees never become 0 for both, so result stays empty
        # then len(result) < len(tasks) path is taken
        tasks = {
            "a": _task("a", children=["b"]),
            "b": _task("b", children=["a"]),
        }
        result = topo_sort(tasks)
        assert len(result) == 2
        in_result = {t.id for t in result}
        assert in_result == {"a", "b"}


if __name__ == "__main__":
    unittest.main()
