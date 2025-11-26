import locale
import unicodedata
from typing import Literal, TypeVar

locale.setlocale(locale.LC_ALL, "")

T = TypeVar("T")
V = TypeVar("V")
Mode = Literal[
    "list",
    "dialog",
    "overlay",
]
DialogKind = Literal[
    "add",
    "edit",
    "request",
]


def _char_width(ch: str) -> int:
    """Calculate the width of a character in the terminal."""
    if len(ch) == 0:
        return 0
    # 制御文字
    if ch < " ":
        return 0
    # 結合文字 (濁点など)
    if unicodedata.combining(ch):
        return 0
    # 東アジア文字幅プロパティ
    # F: full-width, W: wide, A: ambiguous を2倍にして返す
    if unicodedata.east_asian_width(ch) in ("F", "W", "A"):
        return 2
    return 1


def _string_width(s: str) -> int:
    """Calculate the width of a string in the terminal."""
    return sum(map(_char_width, s))
