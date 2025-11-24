import uuid
from datetime import datetime

from pyresults import Err, Ok, Result

from dandori.util.logger import setup_logger
from dandori.util.time import JST

logger = setup_logger(__name__, is_stream=True, is_file=True)


def gen_task_id(username: str) -> str:
    ts = datetime.now(JST).strftime("%Y%m%d%H%M%S")
    return f"{uuid.uuid4()}_{ts}_{username}"


def parse_id(
    s: str,
    *,
    source_ids: list[str],
) -> Result[str, str]:
    s = s.strip()
    if len(s) == 0:
        return Err("Empty ID")
    # full ID search
    candidates = [tid for tid in source_ids if tid == s]
    # 6-chars prefix search
    if len(candidates) == 0 and len(s) == 6:
        candidates = [tid for tid in source_ids if tid[:6] == s]
    # match only one
    if len(candidates) == 1:
        return Ok(candidates[0])
    # multiple matches
    if len(candidates) > 1:
        _msg = f"Ambiguous ID: {s} (multiple tasks. Please set full ID.)"
        return Err(_msg)
    _msg = f"Unknown ID: {s} (please set correct ID.)"
    return Err(_msg)


def parse_ids(
    s: str,
    *,
    source_ids: list[str],
    sep: str = ",",
) -> Result[list[str], str]:
    ids: list[str] = []
    for s6 in s.split(sep):
        match parse_id(s6, source_ids=source_ids):
            case Ok(tid):
                ids.append(tid)
            case Err(e):
                return Err(e)
    return Ok(ids)


def parse_id_with_msg(
    s: str | None,
    *,
    source_ids: list[str],
    msg_buffer: str | None = None,
    can_raise: bool = True,
) -> str:
    if s is None:
        return ""
    match parse_id(s, source_ids=source_ids):
        case Ok(tid):
            return tid  # type: ignore[no-any-return]
        case Err(e):
            if msg_buffer is not None:
                msg_buffer += f"Invalid ID: {e}"
            if can_raise:
                raise ValueError(e)
            return ""
        case _:
            _msg = "Unexpected error"
            if msg_buffer is not None:
                msg_buffer += _msg
            if can_raise:
                raise ValueError(_msg)
            return ""


def parse_ids_with_msg(
    s: str | None,
    *,
    source_ids: list[str],
    sep: str = ",",
    msg_buffer: str | None = None,
    can_raise: bool = True,
) -> list[str]:
    if s is None:
        return []
    match parse_ids(s, source_ids=source_ids, sep=sep):
        case Ok(ids):
            return ids  # type: ignore[no-any-return]
        case Err(e):
            if msg_buffer is not None:
                msg_buffer += f"Invalid IDs: {e}"
            if can_raise:
                raise ValueError(e)
            return []
        case _:
            _msg = "Unexpected error"
            if msg_buffer is not None:
                msg_buffer += _msg
            if can_raise:
                raise ValueError(_msg)
            return []
