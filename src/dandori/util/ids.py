import uuid
from datetime import datetime

from pyresults import Err, Ok, Result

from dandori.util.logger import setup_logger
from dandori.util.time import JST

logger = setup_logger("dandori", is_stream=True, is_file=True)


def gen_task_id(username: str) -> str:
    ts = datetime.now(JST).strftime("%Y%m%d%H%M%S")
    return f"{uuid.uuid4()}_{ts}_{username}"


def parse_id(
    s: str,
    *,
    source_ids: list[str],
    shortend_length: int | None = None,
) -> Result[str, str]:
    s = s.strip()
    if len(s) == 0:
        return Err("Empty ID")
    # full ID search
    candidates = [tid for tid in source_ids if tid == s]
    # LENGTH_SHORTEND_ID-chars prefix search
    if len(candidates) == 0:
        if shortend_length is None:
            pass
        elif len(s) == shortend_length:
            candidates = [tid for tid in source_ids if tid[:shortend_length] == s]
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
    shortend_length: int | None = None,
) -> Result[list[str], str]:
    ids: list[str] = []
    for s_shortend in s.split(sep):
        match parse_id(
            s_shortend,
            source_ids=source_ids,
            shortend_length=shortend_length,
        ):
            case Ok(tid):
                ids.append(tid)
            case Err(e):
                return Err(e)
    return Ok(ids)


def parse_id_with_msg(
    s: str | None,
    *,
    source_ids: list[str],
    shortend_length: int | None = None,
    msg_buffer: str | None = None,
    can_raise: bool = True,
) -> str:
    if s is None:
        return ""
    match parse_id(
        s,
        source_ids=source_ids,
        shortend_length=shortend_length,
    ):
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
    shortend_length: int | None = None,
    msg_buffer: str | None = None,
    can_raise: bool = True,
) -> list[str]:
    if s is None:
        return []
    match parse_ids(
        s,
        source_ids=source_ids,
        sep=sep,
        shortend_length=shortend_length,
    ):
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
