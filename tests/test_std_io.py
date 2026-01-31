import io
import sys
import unittest

from dandori.core.models import Task
from dandori.io.std_io import print_task


def _task(
    assigned_to: str | None = None,
    requested_by: str | None = None,
    tags: list[str] | None = None,
) -> Task:
    return Task(
        id="tid",
        owner="u",
        title="title",
        assigned_to=assigned_to,
        requested_by=requested_by,
        tags=tags or [],
    )


class TestPrintTask(unittest.TestCase):
    def test_prints_required_fields(self) -> None:
        t = _task()
        buf = io.StringIO()

        old = sys.stdout
        sys.stdout = buf
        try:
            print_task(t)
        finally:
            sys.stdout = old
        out = buf.getvalue()
        assert "id: tid" in out
        assert "title: title" in out
        assert "status:" in out
        assert "priority:" in out
        assert "archived:" in out
        assert "due:" in out
        assert "start:" in out
        assert "depends_on:" in out
        assert "children:" in out
        assert "created_at:" in out
        assert "updated_at:" in out

    def test_prints_optional_when_set(self) -> None:
        t = _task(assigned_to="a", requested_by="r", tags=["x"])
        buf = io.StringIO()

        old = sys.stdout
        sys.stdout = buf
        try:
            print_task(t)
        finally:
            sys.stdout = old
        out = buf.getvalue()
        assert "assigned_to: a" in out
        assert "requested_by: r" in out
        assert "tags:" in out
        assert "x" in out

    def test_omits_optional_when_empty(self) -> None:
        t = _task(assigned_to=None, requested_by=None, tags=[])
        buf = io.StringIO()

        old = sys.stdout
        sys.stdout = buf
        try:
            print_task(t)
        finally:
            sys.stdout = old
        out = buf.getvalue()
        assert "assigned_to:" not in out
        assert "requested_by:" not in out
        assert "assigned_to:" not in out
        assert "requested_by:" not in out
        # tags line is omitted when empty (if t.tags is falsy)
        assert out.count("tags:") == 0
