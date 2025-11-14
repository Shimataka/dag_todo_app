import json
from pathlib import Path

from dandori.core.models import Task


def export_json(tasks: dict[str, Task], path: str) -> None:
    data = {tid: t.to_dict() for tid, t in tasks.items()}
    _path = Path(path)
    if not _path.exists():
        _path.touch()
    else:
        _msg = f"File already exists: {_path}"
        raise FileExistsError(_msg)
    with _path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def import_json(path: str) -> dict[str, Task]:
    _path = Path(path)
    if not _path.exists():
        _msg = f"File not found: {_path}"
        raise FileNotFoundError(_msg)
    with _path.open(encoding="utf-8") as f:
        data = json.load(f)
    return {tid: Task.from_dict(td) for tid, td in data.items()}
