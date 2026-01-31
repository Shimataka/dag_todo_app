import os
import tempfile
import unittest
from pathlib import Path

from dandori.core.models import Task
from dandori.storage.sqlite3_store import StoreToSQLite


class TestSQLite3Store(unittest.TestCase):
    """StoreToSQLite の単体メソッド・エラー経路のテスト"""

    def setUp(self) -> None:
        self.original_username = os.environ.get("DD_USERNAME")
        os.environ["DD_USERNAME"] = "test_user"
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")  # noqa: SIM115
        self.temp_file.close()
        self.store = StoreToSQLite(data_path=self.temp_file.name)
        self.store.load()

    def tearDown(self) -> None:
        Path(self.temp_file.name).unlink(missing_ok=True)
        if self.original_username is not None:
            os.environ["DD_USERNAME"] = self.original_username
        elif "DD_USERNAME" in os.environ:
            del os.environ["DD_USERNAME"]

    def test_add_task_duplicate_err(self) -> None:
        t = Task(id="dup", title="T", owner="test_user")
        self.store.add_task(t)
        self.store.commit()
        r = self.store.add_task(t)
        assert r.is_err()
        assert "already exists" in r.unwrap_err().lower()

    def test_add_task_with_depends_on_creates_edges(self) -> None:
        """add_task に depends_on 付きのタスクを渡すと edges に反映される (import/マイグレと YAML 同様)."""
        parent = Task(id="pa", title="Parent", owner="test_user")
        child = Task(id="ch", title="Child", owner="test_user", depends_on=["pa"])
        self.store.add_task(parent)
        self.store.add_task(child)
        self.store.commit()
        ra = self.store.get_task("pa")
        rb = self.store.get_task("ch")
        assert ra.is_ok()
        assert rb.is_ok()
        assert ra.unwrap().children == ["ch"]
        assert rb.unwrap().depends_on == ["pa"]

    def test_get_task_not_found_err(self) -> None:
        r = self.store.get_task("nonexistent")
        assert r.is_err()
        assert "not found" in r.unwrap_err().lower()

    def test_get_tasks_empty_ok(self) -> None:
        r = self.store.get_tasks([])
        assert r.is_ok()
        assert r.unwrap() == []

    def test_get_tasks_partial_ok(self) -> None:
        t1 = Task(id="g1", title="T1", owner="test_user")
        t2 = Task(id="g2", title="T2", owner="test_user")
        self.store.add_task(t1)
        self.store.add_task(t2)
        self.store.commit()
        r = self.store.get_tasks(["g1", "nonexistent", "g2"])
        assert r.is_ok()
        ids = [t.id for t in r.unwrap()]
        assert ids == ["g1", "g2"]

    def test_link_unlink_tasks(self) -> None:
        a = Task(id="la", title="A", owner="test_user")
        b = Task(id="lb", title="B", owner="test_user")
        self.store.add_task(a)
        self.store.add_task(b)
        self.store.commit()
        r = self.store.link_tasks("la", "lb")
        assert r.is_ok()
        ra = self.store.get_task("la")
        rb = self.store.get_task("lb")
        assert ra.unwrap().children == ["lb"]
        assert rb.unwrap().depends_on == ["la"]
        r2 = self.store.unlink_tasks("la", "lb")
        assert r2.is_ok()
        ra2 = self.store.get_task("la")
        rb2 = self.store.get_task("lb")
        assert ra2.unwrap().children == []
        assert rb2.unwrap().depends_on == []

    def test_insert_task(self) -> None:
        a = Task(id="ia", title="A", owner="test_user")
        b = Task(id="ib", title="B", owner="test_user")
        mid = Task(id="imid", title="Mid", owner="test_user")
        self.store.add_task(a)
        self.store.add_task(b)
        self.store.commit()
        self.store.link_tasks("ia", "ib")
        self.store.commit()
        r = self.store.insert_task("ia", "ib", mid)
        assert r.is_ok()
        ra = self.store.get_task("ia")
        rmid = self.store.get_task("imid")
        rb = self.store.get_task("ib")
        assert ra.unwrap().children == ["imid"]
        assert rmid.unwrap().depends_on == ["ia"]
        assert rmid.unwrap().children == ["ib"]
        assert rb.unwrap().depends_on == ["imid"]

    def test_get_dependency_info(self) -> None:
        a = Task(id="da", title="A", owner="test_user")
        b = Task(id="db", title="B", owner="test_user")
        self.store.add_task(a)
        self.store.add_task(b)
        self.store.commit()
        self.store.link_tasks("da", "db")
        self.store.commit()
        r = self.store.get_dependency_info("da")
        assert r.is_ok()
        info = r.unwrap()
        assert "depends_on" in info
        assert "children" in info
        assert "B" in info["children"]

    def test_weakly_connected_component_not_found_err(self) -> None:
        r = self.store.weakly_connected_component("nonexistent")
        assert r.is_err()

    def test_weakly_connected_component_ok(self) -> None:
        a = Task(id="wa", title="A", owner="test_user")
        b = Task(id="wb", title="B", owner="test_user")
        self.store.add_task(a)
        self.store.add_task(b)
        self.store.commit()
        self.store.link_tasks("wa", "wb")
        self.store.commit()
        r = self.store.weakly_connected_component("wa")
        assert r.is_ok()
        comp = r.unwrap()
        assert len(comp) == 2
        ids = {t.id for t in comp}
        assert ids == {"wa", "wb"}

    def test_archive_unarchive_tasks(self) -> None:
        a = Task(id="ar", title="A", owner="test_user")
        self.store.add_task(a)
        self.store.commit()
        r = self.store.archive_tasks("ar")
        assert r.is_ok()
        ra = self.store.get_task("ar")
        assert ra.unwrap().is_archived
        r2 = self.store.unarchive_tasks("ar")
        assert r2.is_ok()
        ra2 = self.store.get_task("ar")
        assert not ra2.unwrap().is_archived

    def test_remove_task(self) -> None:
        t = Task(id="rm", title="T", owner="test_user")
        self.store.add_task(t)
        self.store.commit()
        r = self.store.remove_task("rm")
        assert r.is_ok()
        r2 = self.store.get_task("rm")
        assert r2.is_err()


if __name__ == "__main__":
    unittest.main()
