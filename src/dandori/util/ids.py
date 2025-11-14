import uuid
import zoneinfo
from datetime import datetime

JST = zoneinfo.ZoneInfo("Asia/Tokyo")


def gen_task_id(username: str) -> str:
    ts = datetime.now(JST).strftime("%Y%m%d%H%M%S")
    return f"{uuid.uuid4()}_{ts}_{username}"


def parse_id_pair(a: str, b: str) -> tuple[str, str]:
    return a.strip(), b.strip()
