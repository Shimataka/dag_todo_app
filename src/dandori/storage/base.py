from abc import ABC, abstractmethod

from pyresults import Result

from dandori.core.models import Task
from dandori.util.dirs import ensure_dirs, load_env


class Store(ABC):
    def __init__(
        self,
        data_path: str | None = None,
        archive_path: str | None = None,
    ) -> None:
        ensure_dirs()
        env = load_env()
        self.data_path = data_path or env["DATA_PATH"]
        self.archive_path = archive_path or env["ARCHIVE_PATH"]
        self._tasks: dict[str, Task] = {}

    @abstractmethod
    def load(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def save(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def add_task(self, task: Task, *, id_overwritten: str | None = None) -> Result[None, str]:
        raise NotImplementedError

    @abstractmethod
    def get(self, task_id: str) -> Result[Task, str]:
        raise NotImplementedError

    @abstractmethod
    def get_all_tasks(self) -> Result[dict[str, Task], str]:
        raise NotImplementedError

    @abstractmethod
    def remove(self, task_id: str) -> Result[None, str]:
        raise NotImplementedError

    @abstractmethod
    def link(self, parent_id: str, child_id: str) -> Result[None, str]:
        raise NotImplementedError

    @abstractmethod
    def unlink(self, parent_id: str, child_id: str) -> Result[None, str]:
        raise NotImplementedError

    @abstractmethod
    def archive_component(self, task_id: str, flag: bool) -> Result[list[str], str]:  # noqa: FBT001
        raise NotImplementedError

    @abstractmethod
    def reason(self, task_id: str) -> Result[dict[str, list[str]], str]:
        raise NotImplementedError

    @abstractmethod
    def insert_between(self, a: str, b: str, new_task: Task) -> Result[None, str]:
        raise NotImplementedError
