import zoneinfo
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dandori.core.models import Task

ISO_FMT = "%Y-%m-%dT%H:%M:%S"
JST = zoneinfo.ZoneInfo("Asia/Tokyo")
UTC = zoneinfo.ZoneInfo("UTC")


def now_iso() -> str:
    return datetime.now(JST).strftime(ISO_FMT)


def format_requested_sla(t: "Task") -> str:
    base = ""
    if not t.requested_at:
        return base
    try:
        req = datetime.strptime(t.requested_at, ISO_FMT).astimezone(JST)
        delta = datetime.now(JST) - req
        days = delta.days
        hours = delta.seconds // 3600
        base += f"+{days}d{hours}h"  # 依頼からの経過時間
    except Exception as e:  # noqa: BLE001
        base += f"???h{e!s}"

    if t.due_date:
        try:
            due = datetime.strptime(t.due_date, ISO_FMT).astimezone(JST)
            remain = due - datetime.now(JST)
            rdays = remain.days
            rhours = max(0, remain.seconds // 3600)
            base += f" / SLA:{rdays}d{rhours}h"
        except Exception as e:  # noqa: BLE001
            base += f" / SLA:???{e!s}"
    return base
