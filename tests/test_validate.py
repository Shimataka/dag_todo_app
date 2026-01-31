import unittest

from dandori.core.models import Task
from dandori.core.validate import detect_cycles, detect_inconsistencies


def _task(tid: str, children: list[str] | None = None, depends_on: list[str] | None = None) -> Task:
    return Task(
        id=tid,
        owner="u",
        title=tid,
        children=children or [],
        depends_on=depends_on or [],
    )


class TestDetectCycles(unittest.TestCase):
    def test_no_cycle(self) -> None:
        tasks = {
            "a": _task("a", children=["b"]),
            "b": _task("b", children=["c"], depends_on=["a"]),
            "c": _task("c", depends_on=["b"]),
        }
        assert detect_cycles(tasks) == []

    def test_direct_cycle(self) -> None:
        tasks = {
            "a": _task("a", children=["a"], depends_on=["a"]),
        }
        cycles = detect_cycles(tasks)
        assert len(cycles) == 1
        assert cycles[0] == ["a", "a"]

    def test_simple_cycle(self) -> None:
        tasks = {
            "a": _task("a", children=["b"], depends_on=[]),
            "b": _task("b", children=["a"], depends_on=["a"]),
        }
        cycles = detect_cycles(tasks)
        assert len(cycles) == 1
        assert set(cycles[0]) == {"a", "b"}
        assert cycles[0][0] == cycles[0][-1]

    def test_long_cycle(self) -> None:
        tasks = {
            "a": _task("a", children=["b"]),
            "b": _task("b", children=["c"], depends_on=["a"]),
            "c": _task("c", children=["a"], depends_on=["b"]),
        }
        cycles = detect_cycles(tasks)
        assert len(cycles) == 1
        assert len(cycles[0]) == 4  # a, b, c, a

    def test_multiple_cycles(self) -> None:
        tasks = {
            "a": _task("a", children=["b"]),
            "b": _task("b", children=["a"], depends_on=["a"]),
            "c": _task("c", children=["c"]),
        }
        cycles = detect_cycles(tasks)
        assert len(cycles) >= 1


class TestDetectInconsistencies(unittest.TestCase):
    def test_consistent(self) -> None:
        tasks = {
            "a": _task("a", children=["b"], depends_on=[]),
            "b": _task("b", children=[], depends_on=["a"]),
        }
        assert detect_inconsistencies(tasks) == []

    def test_missing_child(self) -> None:
        # a depends_on b, but b.children does not contain a
        tasks = {
            "a": _task("a", children=[], depends_on=["b"]),
            "b": _task("b", children=[], depends_on=[]),
        }
        out = detect_inconsistencies(tasks)
        assert any(t[1] == "missing_child" and t[2] == "b" for t in out)

    def test_missing_parent(self) -> None:
        # a has child b, but b.depends_on does not contain a
        tasks = {
            "a": _task("a", children=["b"], depends_on=[]),
            "b": _task("b", children=[], depends_on=[]),
        }
        out = detect_inconsistencies(tasks)
        assert any(t[1] == "missing_parent" and t[2] == "b" for t in out)

    def test_skip_when_related_not_in_tasks(self) -> None:
        tasks = {
            "a": _task("a", children=["x"], depends_on=["y"]),
        }
        out = detect_inconsistencies(tasks)
        assert out == []


if __name__ == "__main__":
    unittest.main()
