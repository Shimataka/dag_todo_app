import unittest

from dandori.core.models import Task


class TestTaskFromDict(unittest.TestCase):
    def test_from_dict_missing_required_compensates(self) -> None:
        d: dict = {}
        t = Task.from_dict(d)
        assert t.id
        assert t.owner == "system"
        assert t.title == "temporary title (lack of required fields)"

    def test_from_dict_partial_compensates(self) -> None:
        d = {"id": "custom_id"}
        t = Task.from_dict(d)
        assert t.id == "custom_id"
        assert t.owner == "system"
        assert "temporary" in t.title or t.title


if __name__ == "__main__":
    unittest.main()
