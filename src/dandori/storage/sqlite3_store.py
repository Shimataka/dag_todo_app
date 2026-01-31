from dandori.core.models import Task
from dandori.storage.base import Store


class StoreToSQLite(Store):
    def __init__(self, data_path: str | None = None) -> None:
        super().__init__(data_path)
        self._tasks: dict[str, Task] = {}
        self._tmp_tasks: dict[str, Task] = {}

    def load(self) -> None:
        pass

    def save(self) -> None:
        pass
