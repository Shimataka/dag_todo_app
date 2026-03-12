from typing import Literal

Status = Literal[
    "new",
    "pending",
    "in_progress",
    "done",
    "reviewed",
    "requested",
    "removed",
    "archived",
]

ACTIVE_STATUSES: tuple[Status, ...] = (
    "pending",
    "in_progress",
    "requested",
)
TERMINAL_STATUSES: tuple[Status, ...] = (
    "reviewed",
    "removed",
)
REVIEW_REQUIRED_STATUSES: tuple[Status, ...] = ("done",)
STATUS_MARK_MAP: dict[Status, str] = {
    "new": "+",
    "pending": " ",
    "in_progress": "!",
    "done": ">",
    "reviewed": "✓",
    "requested": "□",
    "removed": "-",
}
STATUS_DISPLAY_ORDER: tuple[Status, ...] = (
    "new",
    "pending",
    "in_progress",
    "done",
    "reviewed",
    "requested",
    "removed",
)


def get_initial_status() -> Status:
    return "new"


def is_active_status(status: Status) -> bool:
    return status in ACTIVE_STATUSES


def is_terminal_status(status: Status) -> bool:
    return status in TERMINAL_STATUSES


def needs_review(status: Status) -> bool:
    return status in REVIEW_REQUIRED_STATUSES


def can_unlock_children(status: Status) -> bool:
    return is_terminal_status(status)


def allowed_next_status(status: Status) -> set[Status]:
    table: dict[Status, set[Status]] = {
        "new": {"pending", "removed"},
        "pending": {"new", "in_progress", "requested", "removed"},
        "in_progress": {"pending", "done", "removed"},
        "done": {"pending", "in_progress", "reviewed"},
        "reviewed": set(),
        "requested": {"pending", "removed"},
        "removed": {"pending"},
    }
    return table[status]


def can_transition(from_status: Status, to_status: Status) -> bool:
    if from_status == to_status:
        return True
    return to_status in allowed_next_status(from_status)


def status_mark(status: Status, *, archived: bool = False) -> str:
    if archived:
        return "A"
    return STATUS_MARK_MAP.get(status, "?")
