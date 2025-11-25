from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from dandori.util.time import now_iso


@dataclass
class Task:
    id: str
    owner: str
    title: str
    description: str = ""
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    done_at: str | None = None
    due_date: str | None = None
    start_at: str | None = None
    priority: int | None = None
    status: Literal["pending", "in_progress", "done", "requested", "removed"] = "pending"
    depends_on: list[str] = field(default_factory=list)  # 複数親OK
    children: list[str] = field(default_factory=list)  # 複数子OK
    is_archived: bool = False
    assigned_to: str | None = None
    requested_by: str | None = None
    requested_at: str | None = None
    requested_note: str | None = None
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Task":
        return Task(**d)
