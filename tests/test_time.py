import re
import unittest
from datetime import datetime, timedelta, timezone

from dandori.core.models import Task
from dandori.util.time import format_requested_sla, now_iso

JST = timezone(timedelta(hours=9))
ISO_FMT = "%Y-%m-%dT%H:%M:%S"


def _task(
    requested_at: str | None = None,
    due_date: str | None = None,
) -> Task:
    return Task(
        id="t1",
        owner="u",
        title="t",
        requested_at=requested_at,
        due_date=due_date,
    )


class TestNowIso(unittest.TestCase):
    def test_format(self) -> None:
        out = now_iso()
        # YYYY-MM-DDTHH:MM:SS
        assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", out)


class TestFormatRequestedSla(unittest.TestCase):
    def test_no_requested_at(self) -> None:
        t = _task(requested_at=None)
        r = format_requested_sla(t)
        assert r.is_ok()
        assert r.unwrap() == ""

    def test_requested_at_only(self) -> None:
        past = (datetime.now(JST) - timedelta(days=1, hours=2)).strftime(ISO_FMT)
        t = _task(requested_at=past)
        r = format_requested_sla(t)
        assert r.is_ok()
        s = r.unwrap()
        assert s.startswith("+")
        assert "d" in s
        assert "h" in s

    def test_with_due_date(self) -> None:
        past = (datetime.now(JST) - timedelta(days=1)).strftime(ISO_FMT)
        future = (datetime.now(JST) + timedelta(days=2, hours=3)).strftime(ISO_FMT)
        t = _task(requested_at=past, due_date=future)
        r = format_requested_sla(t)
        assert r.is_ok()
        s = r.unwrap()
        assert " / SLA:" in s

    def test_parse_error_requested_at(self) -> None:
        t = _task(requested_at="not-a-date")
        r = format_requested_sla(t)
        assert r.is_err()
        assert "???" in r.unwrap_err()

    def test_parse_error_due_date(self) -> None:
        past = (datetime.now(JST) - timedelta(days=1)).strftime(ISO_FMT)
        t = _task(requested_at=past, due_date="invalid")
        r = format_requested_sla(t)
        assert r.is_err()
        assert "SLA:???" in r.unwrap_err()


if __name__ == "__main__":
    unittest.main()
