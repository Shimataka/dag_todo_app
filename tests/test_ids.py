import re
import unittest

import pytest

from dandori.util.ids import (
    gen_task_id,
    parse_id,
    parse_id_with_msg,
    parse_ids,
    parse_ids_with_msg,
)


class TestGenTaskId(unittest.TestCase):
    def test_format(self) -> None:
        out = gen_task_id("alice")
        # uuid_YYYYMMDDHHMMSS_username
        parts = out.split("_")
        assert len(parts) == 3
        uuid_part, ts, username = parts
        assert len(uuid_part) == 36
        assert re.match(r"[0-9a-f-]{36}", uuid_part)
        assert len(ts) == 14
        assert ts.isdigit()
        assert username == "alice"


class TestParseId(unittest.TestCase):
    def test_empty(self) -> None:
        r = parse_id("  ", source_ids=["a", "b"])
        assert r.is_err()
        assert r.unwrap_err() == "Empty ID"

    def test_exact_match(self) -> None:
        r = parse_id("id-1", source_ids=["id-1", "id-2"])
        assert r.is_ok()
        assert r.unwrap() == "id-1"

    def test_prefix_single(self) -> None:
        r = parse_id("id", source_ids=["id-1", "other"])
        assert r.is_ok()
        assert r.unwrap() == "id-1"

    def test_prefix_ambiguous(self) -> None:
        r = parse_id("id", source_ids=["id-1", "id-2"])
        assert r.is_err()
        assert "Ambiguous" in r.unwrap_err()

    def test_unknown(self) -> None:
        r = parse_id("z", source_ids=["a", "b"])
        assert r.is_err()
        assert "Unknown" in r.unwrap_err()


class TestParseIds(unittest.TestCase):
    def test_multiple_ok(self) -> None:
        r = parse_ids("a,b,c", source_ids=["a", "b", "c"])
        assert r.is_ok()
        assert r.unwrap() == ["a", "b", "c"]

    def test_one_err_returns_err(self) -> None:
        r = parse_ids("a,x,c", source_ids=["a", "b", "c"])
        assert r.is_err()
        assert "Unknown" in r.unwrap_err()


class TestParseIdWithMsg(unittest.TestCase):
    def test_none_returns_empty(self) -> None:
        assert parse_id_with_msg(None, source_ids=["a"]) == ""

    def test_ok_returns_id(self) -> None:
        assert parse_id_with_msg("a", source_ids=["a"]) == "a"

    def test_err_can_raise_true_raises(self) -> None:
        with pytest.raises(
            ValueError,
            match=r"Unknown ID: x \(please set correct ID.\)",
        ) as ctx:
            parse_id_with_msg("x", source_ids=["a"], can_raise=True)
        assert "Unknown" in str(ctx.value)

    def test_err_can_raise_false_returns_empty(self) -> None:
        assert parse_id_with_msg("x", source_ids=["a"], can_raise=False) == ""


class TestParseIdsWithMsg(unittest.TestCase):
    def test_none_returns_empty_list(self) -> None:
        assert parse_ids_with_msg(None, source_ids=["a"]) == []

    def test_ok_returns_ids(self) -> None:
        assert parse_ids_with_msg("a,b", source_ids=["a", "b"]) == ["a", "b"]

    def test_err_can_raise_true_raises(self) -> None:
        with pytest.raises(
            ValueError,
            match=r"Unknown ID: x \(please set correct ID.\)",
        ) as ctx:
            parse_ids_with_msg("a,x", source_ids=["a", "b"], can_raise=True)
        assert "Unknown" in str(ctx.value)

    def test_err_can_raise_false_returns_empty_list(self) -> None:
        assert parse_ids_with_msg("x", source_ids=["a"], can_raise=False) == []


if __name__ == "__main__":
    unittest.main()
