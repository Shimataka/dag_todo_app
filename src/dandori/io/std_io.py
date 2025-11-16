# ruff: noqa: T201

from dandori.core.models import Task


def print_task(t: Task) -> None:
    print(f"id: {t.id}")
    print(f"title: {t.title}")
    print(f"status: {t.status}  priority: {t.priority}  archived: {t.is_archived}")
    print(f"due: {t.due_date}  start: {t.start_date}")
    print(f"depends_on: {t.depends_on}")
    print(f"children:   {t.children}")
    print(f"created_at: {t.created_at}  updated_at: {t.updated_at}")
    if t.assigned_to:
        print(f"assigned_to: {t.assigned_to}")
    if t.requested_by:
        print(f"requested_by: {t.requested_by}")
    if t.tags:
        print(f"tags: {t.tags}")
