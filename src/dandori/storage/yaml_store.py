from pathlib import Path

import yaml  # type: ignore[import-untyped]

from dandori.core.models import Task
from dandori.storage.base import Store


class StoreToYAML(Store):
    def __init__(self, data_path: str | None = None) -> None:
        super().__init__(data_path)

    # ---- 基本IO ----

    def load(self) -> None:
        _path = Path(self.data_path)
        if _path.exists():
            with _path.open(encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
                for tid, td in raw.get("tasks", {}).items():
                    self._tasks[tid] = Task.from_dict(td)
        else:
            self._tasks = {}

    def save(self) -> None:
        raw = {"tasks": {tid: t.to_dict() for tid, t in self._tasks.items()}}
        _path = Path(self.data_path)
        with _path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(raw, f, allow_unicode=True, sort_keys=True)
