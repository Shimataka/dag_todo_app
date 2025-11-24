import argparse
import curses
import locale
import logging
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, TypeVar

from dandori.core.models import Task
from dandori.core.ops import (
    OpsError,
    add_task,
    archive_tree,
    get_children,
    get_deps,
    list_tasks,
    set_requested,
    set_status,
    unarchive_tree,
    update_task,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
file_handler = logging.FileHandler("tui.log")
file_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

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


STATUS_MARK_MAP = {
    "pending": "-",
    "in_progress": "I",
    "done": "D",
    "requested": "R",
    "removed": "X",
    "archived": "A",
}

MAIN_THEME_COLOR = 1
ADD_TASK_COLOR = 4
SELECTED_ROW_COLOR = 3
SURPRESSED_COLOR = 4
COMPLETED_COLOR = 5
REQUESTED_COLOR = 10
WORKING_COLOR = 6
WAITING_COLOR = 7
DIALOG_BG_COLOR = 8
OVERLAY_BG_COLOR = 9


class HeaderLines:
    """Header lines for the TUI."""

    @classmethod
    def height(cls) -> int:
        return 3

    @classmethod
    def title(cls) -> str:
        return "--- dandori (TUI) > Topological graph TODO task manager ---"

    @classmethod
    def status(
        cls,
        status_label: str,
        archived_label: str,
        topo_label: str,
        req_label: str,
    ) -> str:
        return cls._status_line(status_label, archived_label, topo_label, req_label)

    @classmethod
    def help(cls) -> str:
        return cls._help_line()

    @classmethod
    def _status_line(
        cls,
        status_label: str,
        archived_label: str,
        topo_label: str,
        req_label: str,
    ) -> str:
        status_line = "List: [↑/↓ Move, [/] Scroll] "
        status_line += f"[(f/F)ilter: {status_label}] [(a)rchived: {archived_label}] "
        status_line += f"[(t)opo: {topo_label}] [(r)equested: {req_label}]"
        return status_line

    @classmethod
    def _help_line(cls) -> str:
        help_line = "Task: [(A)dd] [(E)dit] [(R)equest] [(G)raph] "
        help_line += "[(p)end] [(i)n_progress] [(d)one] [(x)Archive] [u Unarchive] [q Quit]"
        return help_line


@dataclass
class OverlayState:
    """Read-only overlay to show local graph (deps/children) etc."""

    title: str
    lines: list[str]


@dataclass
class FilterState:
    status: str | None = None  # None=すべて/pending/in_progress/done/requested/removed ステータスフィルタ
    archived: bool | None = None  # None=すべて/False=unarchived/True=archived
    requested_only: bool = False  # requested ステータスのみ表示フラグ
    topo: bool = False  # トポロジカルソート表示フラグ
    tags: list[str] = field(default_factory=list)  # タグフィルタ


@dataclass
class FieldState:
    """Single-line field in a dialog form."""

    name: str  # title, description, priorityなど
    label: str  # 画面表示用ラベル
    buffer: str = ""  # 編集中テキスト
    cursor: int = 0  # カーソル位置


@dataclass
class DialogState:
    kind: DialogKind
    title: str
    fields: list[FieldState] = field(default_factory=list)
    current_index: int = 0  # 現在のフィールドインデックス
    target_task_id: str | None = None  # 編集対象のタスクID


@dataclass
class AppState:
    tasks: list[Task] = field(default_factory=list)
    selected_index: int = 0
    mode: Mode = "list"
    filter: FilterState = field(default_factory=FilterState)
    dialog: DialogState | None = None
    overlay: OverlayState | None = None

    # UI用
    msg_footer: str | None = None  # フッターメッセージ表示
    window_list_width: int = 0
    window_list_height: int = 0
    window_detail_width: int = 0
    window_detail_height: int = 0

    # scroll用
    list_offset: int = 0  # list viewのstart rowのオフセット
    detail_offset: int = 0  # detail viewのstart rowのオフセット


class App:
    def __init__(
        self,
        stdscr: curses.window,
        args: argparse.Namespace | None = None,
    ) -> None:
        self.stdscr = stdscr
        self.args = args
        self.state = AppState()
        self._init_curses()
        self._reload_tasks()

    # ---- cursor management ---------------------------------------------
    def _cursor_off(self) -> None:
        curses.curs_set(0)

    def _init_curses(self) -> None:
        # 色やキーパッドの設定で、画面サイズ対応もあればここ。
        curses.curs_set(0)
        self.stdscr.keypad(True)  # noqa: FBT003

        if curses.has_colors():
            curses.start_color()
            curses.use_default_colors()
            # color pair indexes (idx, foreground, background) with ANSI color codes
            curses.init_pair(MAIN_THEME_COLOR, 166, -1)  # header
            curses.init_pair(ADD_TASK_COLOR, 166, -1)  # add-task
            curses.init_pair(SELECTED_ROW_COLOR, -1, 7)  # selected-row
            curses.init_pair(SURPRESSED_COLOR, 8, -1)  # archived/removed
            curses.init_pair(COMPLETED_COLOR, 10, -1)  # done
            curses.init_pair(REQUESTED_COLOR, 12, -1)  # requested
            curses.init_pair(WORKING_COLOR, 9, -1)  # in_progress
            curses.init_pair(WAITING_COLOR, 15, -1)  # pending
            curses.init_pair(DIALOG_BG_COLOR, -1, 236)  # dialog-bg
            curses.init_pair(OVERLAY_BG_COLOR, -1, 236)  # overlay-bg

    def _reload_tasks(self, keep_task_id: str | None = None) -> None:
        """Reload tasks from backend according to filter."""
        # FilterState に基づいて core.ops.list_tasks() を呼んで state.tasks を更新
        self.state.tasks = list_tasks(
            status=self.state.filter.status,  # type: ignore[arg-type]
            archived=self.state.filter.archived,
            topo=self.state.filter.topo,
            requested_only=self.state.filter.requested_only,
        )

        # clamp / restore selection index
        if not self.state.tasks:
            self.state.selected_index = 0
            self.state.list_offset = 0
            self.state.detail_offset = 0
            return
        # できるだけ同じタスクIDを再選択する
        if keep_task_id is not None:
            for idx, t in enumerate[Task](self.state.tasks):
                if t.id == keep_task_id:
                    # index 0 はルートタスク追加用のダミー行として扱う
                    self.state.selected_index = idx + 1
                    break
            else:
                # 見つからなければ clamp
                self.state.selected_index = max(
                    0,
                    min(self.state.selected_index, len(self.state.tasks)),
                )
        else:
            self.state.selected_index = max(
                0,
                min(self.state.selected_index, len(self.state.tasks)),
            )

        # reload時は先頭から表示し直す
        self.state.list_offset = 0
        self.state.detail_offset = 0

    def _safe_addnstr(self, y: int, x: int, s: str, n: int) -> None:
        # 画面サイズを更新
        max_y, max_x = self.stdscr.getmaxyx()
        self.state.window_list_width = max_x // 2
        self.state.window_detail_width = max_x - self.state.window_list_width
        self.state.window_list_height = max_y - 1
        self.state.window_detail_height = max_y - 1

        # 画面外なら描かない
        if y < 0 or y >= max_y or x < 0 or x >= max_x:
            return
        # 右端を超えないようにクリップ
        limit = max_x - x
        if limit <= 0 or n <= 0:
            return
        # 最終行では右端1マスを開ける
        if y == max_y - 1 and limit == max_x:
            limit -= 1
        s = s.replace("\t", " ")  # タブがいると幅が読めないので潰す
        n = min(n, len(s), limit)
        if n <= 0:
            return
        # nを減らしながらトライ (例外が発生したら1文字ずつ減らして再試行)
        while n > 0:
            chunk = s[:n]
            try:
                self.stdscr.addnstr(y, x, chunk, n)
            except curses.error:
                n -= 1
            else:
                return

    def draw(self) -> None:
        self.stdscr.erase()
        max_y, max_x = self.stdscr.getmaxyx()
        if max_y < 2 or max_x < 2:
            # 端末サイズが小さすぎる場合は描画を諦める
            self.stdscr.refresh()
            return

        header_height = HeaderLines.height()
        footer_height = 1
        content_height = max_y - header_height - footer_height
        if content_height <= 0 or max_x <= 0:
            self.stdscr.refresh()
            return

        list_width = max_x // 2
        detail_width = max_x - list_width

        self._draw_header(0, max_x)
        self._draw_footer(max_y - 1, max_x)
        self._draw_list(header_height, content_height, list_width)
        self._draw_detail(header_height, content_height, list_width, detail_width)

        if self.state.mode == "dialog" and self.state.dialog is not None:
            self._draw_dialog(header_height, content_height, max_x)
        else:
            # dialogでないならカーソルを隠す
            try:
                self._cursor_off()
            except curses.error:
                logger.exception("Error (cursor off)")
                self.state.msg_footer = "Error (cursor off)"
        if self.state.mode == "overlay" and self.state.overlay is not None:
            self._draw_overlay(header_height, content_height, max_x)

        self.stdscr.refresh()

    def _draw_header(self, y: int, width: int) -> None:
        f = self.state.filter

        # status表示
        status_label_map = {
            None: "all",
            "pending": "pending",
            "in_progress": "in_progress",
            "done": "done",
            "requested": "requested",
            "removed": "removed",
        }
        status_label = status_label_map.get(f.status, "all")

        # archived表示
        if f.archived is True:
            archived_label = "archived"
        elif f.archived is False:
            archived_label = "active"
        else:
            archived_label = "all"

        # requested_only表示
        req_label = "on" if f.requested_only else "off"

        # topo表示
        topo_label = "on" if f.topo else "off"

        # ヘッダータイトルを作成
        title = HeaderLines.title()
        status = HeaderLines.status(status_label, archived_label, topo_label, req_label)
        helps = HeaderLines.help()

        if curses.has_colors():
            self.stdscr.attron(curses.color_pair(MAIN_THEME_COLOR))
        self._safe_addnstr(y, 0, title.ljust(width), width)
        self._safe_addnstr(y + 1, 0, status.ljust(width), width)
        self._safe_addnstr(y + 2, 0, helps.ljust(width), width)
        if curses.has_colors():
            self.stdscr.attroff(curses.color_pair(MAIN_THEME_COLOR))

    def _draw_footer(self, y: int, width: int) -> None:
        msg = self.state.msg_footer or ""
        if curses.has_colors():
            self.stdscr.attron(0)
        self._safe_addnstr(y, 0, msg.ljust(width), width)
        if curses.has_colors():
            self.stdscr.attroff(0)

    def _draw_list(  # noqa: C901
        self,
        y: int,
        height: int,
        width: int,
    ) -> None:
        tasks = self.state.tasks

        # 全行数 (0: ダミー行, 1..len(tasks): 実タスク行)
        total_rows = len(tasks) + 1  # +1 はルートタスク追加用のダミー行
        if total_rows <= 0 or height <= 0:
            return

        # selected_indexをclamp
        self.state.selected_index = max(0, min(self.state.selected_index, total_rows - 1))

        # list_offsetをclamp
        if self.state.selected_index < self.state.list_offset:
            self.state.list_offset = self.state.selected_index
        elif self.state.selected_index >= self.state.list_offset + height:
            self.state.list_offset = self.state.selected_index - height + 1

        self.state.list_offset = max(0, min(self.state.list_offset, max(0, total_rows - height)))

        start = self.state.list_offset
        end = min(start + height, total_rows)

        for i, idx in enumerate[int](range(start, end)):
            try:
                t = tasks[idx - 1]
            except IndexError:
                t = Task(id="Unknown", title=f"IndexError with idx={idx - 1}")
            row_y = y + i

            attrs = 0
            # color on
            if curses.has_colors():
                # add task
                if idx == 0:
                    attrs |= curses.color_pair(ADD_TASK_COLOR)
                # done
                elif t.status == "done":
                    attrs |= curses.color_pair(COMPLETED_COLOR)
                # requested
                elif t.status == "requested":
                    attrs |= curses.color_pair(REQUESTED_COLOR)
                # archived
                elif t.is_archived:
                    attrs |= curses.color_pair(SURPRESSED_COLOR)
                # in_progress
                elif t.status == "in_progress":
                    attrs |= curses.color_pair(WORKING_COLOR)
                # pending
                elif t.status == "pending":
                    attrs |= curses.color_pair(WAITING_COLOR)
                # selected row --> fg/bg reversed
                if idx == self.state.selected_index:
                    attrs |= curses.A_REVERSE
                if attrs:
                    self.stdscr.attron(attrs)

            # charactor in list line
            if idx == 0:
                line = "[--- Add a task (Enter or 'A' key) ---]"
                self._safe_addnstr(row_y, 0, line.ljust(width), width)
            else:
                line = self._format_list_line(t, width)
                self._safe_addnstr(row_y, 0, line.ljust(width), width)

            # color off
            if attrs:
                self.stdscr.attroff(attrs)

    def _format_list_line(self, t: Task, width: int) -> str:
        # status/archived marks
        marks: list[str] = []
        if t.is_archived:
            marks.append("A")
        status_str = STATUS_MARK_MAP.get(t.status, "?")

        short_id = t.id[:6]
        title = t.title.replace("\n", " ")

        line = f"{status_str} {short_id:<6} {title}"
        return line[:width]

    def _draw_detail(  # noqa: C901
        self,
        y: int,
        height: int,
        x: int,
        width: int,
    ) -> None:
        if height <= 0 or width <= 0:
            return
        for row in range(height):
            if curses.has_colors():
                self.stdscr.attron(0)
            self._safe_addnstr(y + row, x, " " * width, width)
            if curses.has_colors():
                self.stdscr.attroff(0)

        if not self.state.tasks:
            text = "(no tasks)"
            if curses.has_colors():
                self.stdscr.attron(0)
            self._safe_addnstr(y, x, text.ljust(width), width)
            if curses.has_colors():
                self.stdscr.attroff(0)
            return

        t = self._current_task()
        if t is None:
            text = "<If enter/'a' is pressed, you can add a new root task>"
            self._safe_addnstr(y, x, text.ljust(width), width)
            return

        # 表示用の視覚行 (wrap 済み) を構成
        visual_lines = self._build_detail_lines(t, width)
        if not visual_lines:
            visual_lines = ["(no details)"]

        # detail_offset をクランプ
        max_offset = max(0, len(visual_lines) - max(0, height))
        self.state.detail_offset = max(0, min(self.state.detail_offset, max_offset))

        start = self.state.detail_offset
        end = min(start + height, len(visual_lines))

        row = 0
        for line in visual_lines[start:end]:
            if row >= height:
                break
            start = 0
            while start < len(line) and row < height:
                chunk = line[start : start + width]
                if curses.has_colors():
                    self.stdscr.attron(0)
                self._safe_addnstr(y + row, x, chunk, width)
                if curses.has_colors():
                    self.stdscr.attroff(0)
                start += width
                row += 1

    def _build_detail_lines(  # noqa: C901
        self,
        t: Task,
        width: int,
    ) -> list[str]:
        """Build wrapped detail lines for a task."""
        base: list[str] = []
        base.append(f"ID: {t.id}")
        base.append(f"Title: {t.title}")
        status: str = t.status
        if t.is_archived:
            status += " (archived)"
        base.append(f"Status: {status}")
        base.append(f"Priority: {t.priority}")
        if t.start_date:
            base.append(f"Start: {t.start_date}")
        if t.due_date:
            base.append(f"Due:   {t.due_date}")
        if t.tags:
            base.append("Tags: " + ", ".join(t.tags))
        if t.depends_on:
            base.append("Depends on: " + ", ".join(t.depends_on))
        if t.children:
            base.append("Children:   " + ", ".join(t.children))
        if t.description:
            base.append("")
            base.append("Description:")
            base.extend(["  " + line for line in t.description.splitlines()])

        visual: list[str] = []
        for line in base:
            if not line:
                visual.append("")
                continue
            s = line
            while s:
                chunk = s[:width]
                visual.append(chunk)
                s = s[width:]
        return visual

    def _scroll_detail(self, delta: int) -> None:
        """Scroll detail view by delta visual lines."""
        if delta == 0:
            return

        t = self._current_task()
        if t is None:
            return

        max_y, max_x = self.stdscr.getmaxyx()
        header_height = HeaderLines.height()
        footer_height = 1
        content_height = max_y - header_height - footer_height
        if content_height <= 0 or max_x <= 0:
            return

        list_width = max_x // 2
        detail_width = max_x - list_width

        visual_lines = self._build_detail_lines(t, detail_width)
        if not visual_lines:
            return

        max_offset = max(0, len(visual_lines) - max(0, content_height))
        new_offset = self.state.detail_offset + delta
        self.state.detail_offset = max(0, min(new_offset, max_offset))

    # ---- dialog ---------------------------------------------------------

    def _draw_dialog(self, content_y: int, content_height: int, max_x: int) -> None:
        """Draw simple centered one-line input dialog."""
        dlg = self.state.dialog
        if dlg is None:
            return

        num_fields = len(dlg.fields)
        if num_fields == 0:
            return
        box_width = min(80, max_x - 4)
        box_height = 3 + num_fields + 1  # title + empty + fields + hint
        top = content_y + max(0, (content_height - box_height) // 2)
        left = max(2, (max_x - box_width) // 2)

        # bg color on
        attr = 0
        if curses.has_colors():
            attr |= curses.color_pair(DIALOG_BG_COLOR)
        self.stdscr.attron(attr)

        # 枠線と中線をクリア
        for row in range(box_height):
            self._safe_addnstr(top + row, left, " " * box_width, box_width)

        # タイトル
        title = f"[{dlg.title}]"
        self._safe_addnstr(top, left, title.ljust(box_width), box_width)
        # 空行
        self._safe_addnstr(top + 1, left, " " * box_width, box_width)
        # フィールド群
        max_input_width = box_width - 18  # ラベル用の適用な余白
        row = top + 2
        for idx, fs in enumerate[FieldState](dlg.fields):
            marker = ">" if idx == dlg.current_index else " "
            label = f"{marker} {fs.label}: "
            value = fs.buffer
            if len(value) > max_input_width:
                value = value[-max_input_width:]
            line = (label + value)[:box_width]
            self._safe_addnstr(row, left, line.ljust(box_width), box_width)
            row += 1

        # ヒント
        hint = "[Tab/↑/↓: Move, Enter: Apply, Esc: Cancel]"
        self._safe_addnstr(top + box_height - 1, left, hint.ljust(box_width), box_width)

        # bg color off
        if curses.has_colors() and attr:
            self.stdscr.attroff(attr)

        # ---- draw text cursor ---------------------------------------------
        # 現在のフィールドのカーソル位置に物理カーソルを移動
        try:
            dlg = self.state.dialog
            if dlg is not None:
                fs = dlg.fields[dlg.current_index]
                # カーソル位置計算
                cursor_row = top + 2 + dlg.current_index
                # label + marker + space
                label_prefix = f"> {fs.label}: " if dlg.current_index == dlg.current_index else f"  {fs.label}: "
                # 入力欄の左端 = left + len(label_prefix)
                cursor_col = left + _string_width(label_prefix)
                # buffer内のカーソル位置
                cursor_col += _string_width(fs.buffer[: fs.cursor])
                # 物理カーソル表示
                curses.curs_set(1)
                self.stdscr.move(cursor_row, cursor_col)
        except curses.error as e:
            # ターミナルによってはカーソル制御に失敗するかも
            _msg = f"Error (draw text cursor): {e}"
            logger.exception(_msg)
            self.state.msg_footer = _msg

    # ---- overlay --------------------------------------------------------

    def _draw_overlay(self, content_y: int, content_height: int, max_x: int) -> None:
        """Draw small overlay to show local graph (deps/children) etc."""
        ov = self.state.overlay
        if ov is None or not ov.lines:
            return

        # bg color on
        attr = 0
        if curses.has_colors():
            attr |= curses.color_pair(OVERLAY_BG_COLOR)
        self.stdscr.attron(attr)

        # 行数で高さを決める
        box_width = min(100, max_x - 4)
        max_box_height = content_height
        needed_height = min(len(ov.lines) + 2, max_box_height)
        box_height = max(3, needed_height)

        top = content_y + max(0, (content_height - box_height) // 2)
        left = max(2, (max_x - box_width) // 2)

        # クリア
        for row in range(box_height):
            self._safe_addnstr(top + row, left, " " * box_width, box_width)

        # タイトル
        title = f"[{ov.title}]"
        self._safe_addnstr(top, left, title.ljust(box_width), box_width)

        # 本文
        start_row = top + 1
        row = start_row
        for line in ov.lines[: box_height - 2]:
            self._safe_addnstr(row, left, line.ljust(box_width), box_width)
            row += 1

        # ヒント
        hint = "[ESC key: close]"
        self._safe_addnstr(top + box_height - 1, left, hint.ljust(box_width), box_width)

        # bg color off
        if curses.has_colors() and attr:
            self.stdscr.attroff(attr)

    # ---- overlay helpers ------------------------------------------------

    def _start_graph_overlay(self) -> None:
        """Show local graph (deps and children) for current task."""
        task = self._current_task()
        if task is None:
            self.state.msg_footer = "No task selected"
            return

        try:
            deps = get_deps(task.id)
            children = get_children(task.id)
        except OpsError as e:
            self.state.msg_footer = f"Error (graph): {e}"
            return

        lines: list[str] = []
        lines.append("-" * 13)  # 13は"(Depended by)"の長さ
        # ---
        lines.append("(Depends on)")
        if deps:
            for d in deps:
                s = f"  ^ [{STATUS_MARK_MAP.get(d.status, '?')}] "
                s += f"({d.id[:6]:<6}) "
                s += f"{d.title} "
                s += f"[{d.due_date}]" if d.due_date else ""
                lines.append(s)
        else:
            lines.append("  ^")
        # ---
        lines.append("(Selected)")
        s = f"  - [{STATUS_MARK_MAP.get(task.status, '?')}] "
        s += f"({task.id[:6]:<6}) "
        s += f"{task.title} "
        s += f"[{task.due_date}]" if task.due_date else ""
        lines.append(s)
        # ---
        lines.append("(Depended by)")
        if children:
            for c in children:
                s = f"  v [{STATUS_MARK_MAP.get(c.status, '?')}] "
                s += f"({c.id[:6]:<6}) "
                s += f"{c.title} "
                s += f"[{c.due_date}]" if c.due_date else ""
                lines.append(s)
        else:
            lines.append("  v")
        # ---
        lines.append("-" * 12)  # 12は"Depended by:"の長さ

        self.state.overlay = OverlayState(
            title="Local DAG (deps/children)",
            lines=lines,
        )
        self.state.mode = "overlay"

    def _handle_overlay_key(self, key: int) -> None:
        """Close overlay on any key."""
        if key in (27,):  # ESC
            self.state.mode = "list"
            self.state.overlay = None
            return

    # ---- small helpers --------------------------------------------------

    def _current_task(self) -> Task | None:
        """Return currently selected task or None."""
        tasks = self.state.tasks
        if not tasks:
            return None
        # index 0 はルートタスク追加用のダミー行として扱う
        idx = self.state.selected_index
        if idx <= 0:
            return None
        real_idx = idx - 1
        if not (0 <= real_idx < len(tasks)):
            return None
        return self.state.tasks[real_idx]

    def _start_add_dialog(self) -> None:
        """Open dialog to add a new top-level task"""
        fields = [
            FieldState(
                name="title",
                label="Title                   ",
                buffer="",
                cursor=0,
            ),
            FieldState(
                name="priority",
                label="Priority (0-9)          ",
                buffer="",
                cursor=0,
            ),
            FieldState(
                name="start_date",
                label="Start Date (ISO format) ",
                buffer="",
                cursor=0,
            ),
            FieldState(
                name="due_date",
                label="Due Date (ISO format)   ",
                buffer="",
                cursor=0,
            ),
            FieldState(
                name="tags",
                label="Tags (',' separated)    ",
                buffer="",
                cursor=0,
            ),
            FieldState(
                name="description",
                label="Description             ",
                buffer="",
                cursor=0,
            ),
        ]
        self.state.dialog = DialogState(
            kind="add",
            title="Add New Task",
            fields=fields,
            current_index=0,
            target_task_id=None,
        )
        self.state.mode = "dialog"

    def _start_edit_dialog(self) -> None:
        """Open dialog to edit the current task"""
        task = self._current_task()
        if task is None:
            self.state.msg_footer = "No task selected"
            return
        fields = [
            FieldState(
                name="title",
                label="Title                      ",
                buffer=task.title,
                cursor=len(task.title),
            ),
            FieldState(
                name="priority",
                label="Priority (0-9)             ",
                buffer=str(task.priority),
                cursor=len(str(task.priority)),
            ),
            FieldState(
                name="start_date",
                label="Start Date (ISO format)    ",
                buffer=task.start_date or "",
                cursor=len(task.start_date or ""),
            ),
            FieldState(
                name="due_date",
                label="Due Date (ISO format)      ",
                buffer=task.due_date or "",
                cursor=len(task.due_date or ""),
            ),
            FieldState(
                name="tags",
                label="Tags (',' separated)       ",
                buffer=", ".join(task.tags),
                cursor=len(", ".join(task.tags)),
            ),
            FieldState(
                name="description",
                label="Description                ",
                buffer=task.description,
                cursor=len(task.description),
            ),
            FieldState(
                name="depends_on",
                label="Depends on (6-chars, ',')  ",
                buffer=", ".join([t[:6] for t in task.depends_on]),
                cursor=len(", ".join([t[:6] for t in task.depends_on])),
            ),
            FieldState(
                name="children",
                label="Children (6-chars, ',')    ",
                buffer=", ".join([t[:6] for t in task.children]),
                cursor=len(", ".join([t[:6] for t in task.children])),
            ),
        ]
        self.state.dialog = DialogState(
            kind="edit",
            title="Edit Task",
            fields=fields,
            current_index=0,
            target_task_id=task.id,
        )
        self.state.mode = "dialog"

    def _start_request_dialog(self) -> None:
        """Open dialog to mark current task as requested (assignee + note)"""
        task = self._current_task()
        if task is None:
            self.state.msg_footer = "No task selected"
            return
        # 既知情報を初期値として利用
        initial_assignee = task.assigned_to or ""
        initial_note = task.requested_note or ""
        fields = [
            FieldState(
                name="assignee",
                label="Assignee ",
                buffer=initial_assignee,
                cursor=len(initial_assignee),
            ),
            FieldState(
                name="note",
                label="Note     ",
                buffer=initial_note,
                cursor=len(initial_note),
            ),
        ]
        self.state.dialog = DialogState(
            kind="request",
            title="Request Task",
            fields=fields,
            current_index=0,
            target_task_id=task.id,
        )
        self.state.mode = "dialog"

    def _parse_field(
        self,
        values: dict[str, str],
        key: str,
        parser: Callable[[str], T],
        default: V,
        error_template: str,
    ) -> T | V:
        if (value_str := values.get(key)) and value_str != "":
            try:
                return parser(value_str)
            except ValueError:
                self.state.msg_footer = f"{error_template.format(value_str)}: canceled"
                raise
        return default

    def _parse_ids(self, s: str, *, sep: str = ",") -> list[str]:
        tasks = self.state.tasks
        ids: list[str] = []
        for s6 in s.split(sep):
            s6 = s6.strip()
            if len(s6) == 0:
                continue
            # full ID search
            candidates = [tt.id for tt in tasks if tt.id == s6]
            # 6-chars prefix search
            if len(candidates) == 0 and len(s6) == 6:
                candidates = [tt.id for tt in tasks if tt.id[:6] == s6]
            # match only one
            if len(candidates) == 1:
                ids.append(candidates[0])
            # multiple matches
            elif len(candidates) > 1:
                self.state.msg_footer = f"Ambiguous ID: {s6} (multiple tasks. Please set full ID.)"
                return []
            else:
                self.state.msg_footer = f"Unknown ID: {s6} (please set correct ID.)"
                return []
        return ids

    def _apply_dialog(self) -> None:  # noqa: C901
        """Apply the dialog result (add/edit)"""
        dlg = self.state.dialog
        if dlg is None:
            return
        # フィールドをdictにまとめる
        values: dict[str, str] = {f.name: f.buffer.strip() for f in dlg.fields}
        # priority (optional)
        priority = self._parse_field(
            values,
            "priority",
            int,
            None,
            "Invalid priority value '{}'",
        )
        # start_date (optional)
        start_date = self._parse_field(
            values,
            "start_date",
            datetime.fromisoformat,
            None,
            "Invalid start date value '{}'",
        )
        # due_date (optional)
        due_date = self._parse_field(
            values,
            "due_date",
            datetime.fromisoformat,
            None,
            "Invalid due date value '{}'",
        )
        # tags (optional)
        tags = self._parse_field(
            values,
            "tags",
            lambda s: [t.strip() for t in s.split(",")],
            None,
            "Invalid tags value '{}'",
        )
        # assignee (optional)
        assignee = self._parse_field(
            values,
            "assignee",
            str,
            None,
            "Invalid assignee value '{}'",
        )
        # note (optional)
        note = self._parse_field(
            values,
            "note",
            str,
            None,
            "Invalid note value '{}'",
        )

        # depends_on (optional)
        depends_on = self._parse_field(
            values,
            "depends_on",
            lambda s: self._parse_ids(s, sep=","),
            None,
            "Invalid depends_on value '{}'",
        )
        # children (optional)
        children = self._parse_field(
            values,
            "children",
            lambda s: self._parse_ids(s, sep=","),
            None,
            "Invalid children value '{}'",
        )

        # add task
        if dlg.kind == "add":
            # title (required)
            if (title := values.get("title")) is None:
                self.state.msg_footer = "Empty title: canceled"
                return
            # 親は「現在選択中のタスク」で、なければルートタスク
            parent_ids: list[str] = []
            current = self._current_task()
            if current is not None:
                parent_ids = [current.id]

            try:
                task = add_task(
                    title=title,
                    parent_ids=parent_ids,
                    description=values.get("description") or "",
                    priority=priority,
                    start=start_date,
                    due=due_date,
                    tags=tags,
                )
            except OpsError as e:
                self.state.msg_footer = f"Error (add): {e}"
                return
            else:
                self.state.msg_footer = f"Added: {task.id[:6]:<6}"
                self._reload_tasks(keep_task_id=task.id)
        # edit task
        elif dlg.kind == "edit":
            # title (required)
            if (title := values.get("title")) is None:
                self.state.msg_footer = "Empty title: canceled"
                return
            if dlg.target_task_id is None:
                self.state.msg_footer = "No task selected for edit"
                return
            try:
                task = update_task(
                    dlg.target_task_id,
                    title=title,
                    description=values.get("description") or "",
                    priority=priority,
                    start=start_date,
                    due=due_date,
                    tags=tags,
                    parent_ids=depends_on,
                    children_ids=children,
                )
            except OpsError as e:
                self.state.msg_footer = f"Error (edit): {e}"
                return
            else:
                self.state.msg_footer = f"Updated: {task.id[:6]}"
                self._reload_tasks(keep_task_id=task.id)
        elif dlg.kind == "request":
            # title (required)
            if dlg.target_task_id is None:
                self.state.msg_footer = "No task selected for request"
                return
            try:
                # requested_by はset_requested内部でenvから補完してもらう
                set_requested(
                    dlg.target_task_id,
                    requested_to=assignee,
                    note=note,
                    due=due_date,
                    requested_by=None,
                )
            except OpsError as e:
                self.state.msg_footer = f"Error (request): {e}"
                return
            else:
                self.state.msg_footer = f"Requested: {dlg.target_task_id[:6]:<6}"
                self._reload_tasks(keep_task_id=dlg.target_task_id)

        else:
            _msg = f"Invalid dialog kind: {dlg.kind}"  # type: ignore[unreachable]
            logger.error(_msg)
            self.state.msg_footer = _msg
            return

    def _handle_dialog_key(self, key: int, ch: str | None = None) -> None:  # noqa: C901
        """Handle key press while dialog is active."""
        dlg = self.state.dialog
        if dlg is None:
            return

        fs = dlg.fields[dlg.current_index]

        # Enter: apply
        if key in (curses.KEY_ENTER, 10, 13):
            self._apply_dialog()
            # ダイアログを閉じる
            self.state.dialog = None
            self.state.mode = "list"
            return

        # Esc: cancel
        if key in (27,):
            self.state.msg_footer = "Canceled"
            self.state.dialog = None
            self.state.mode = "list"
            return

        # フィールド移動
        if key in (curses.KEY_DOWN, 9):  # Down Arrow or Tab
            dlg.current_index = (dlg.current_index + 1) % len(dlg.fields)
            # カーソルは語尾におく
            f = dlg.fields[dlg.current_index]
            f.cursor = len(f.buffer)
            return
        if key in (curses.KEY_UP,):  # Up Arrow
            dlg.current_index = (dlg.current_index - 1) % len(dlg.fields)
            # カーソルは語尾におく
            f = dlg.fields[dlg.current_index]
            f.cursor = len(f.buffer)
            return

        # Backspace: delete left char
        if key in (curses.KEY_BACKSPACE, 127, 8):
            if fs.cursor > 0:
                fs.buffer = fs.buffer[: fs.cursor - 1] + fs.buffer[fs.cursor :]
                fs.cursor -= 1
            return
        # Delete: delete right char
        if key in (curses.KEY_DC,):
            if fs.cursor < len(fs.buffer):
                fs.buffer = fs.buffer[: fs.cursor] + fs.buffer[fs.cursor + 1 :]
            return

        # 左右移動
        if key == curses.KEY_LEFT:
            if fs.cursor > 0:
                fs.cursor -= 1
            return
        if key == curses.KEY_RIGHT:
            if fs.cursor < len(fs.buffer):
                fs.cursor += 1
            return
        if key == curses.KEY_HOME:
            fs.cursor = 0
            return
        if key == curses.KEY_END:
            fs.cursor = len(fs.buffer)
            return

        # 文字入力 (ASCII 32-126)
        # chがstrのときはget_wch()からきた通常文字として扱う
        insert_ch: str | None = None
        if ch is not None:
            insert_ch = ch
        else:
            # 従来互換: int だけ渡ってきた場合はASCII文字として扱う
            if 32 <= key <= 126:
                insert_ch = chr(key)

        if insert_ch is not None and len(insert_ch) > 0:
            if insert_ch < " ":
                return
            fs.buffer = fs.buffer[: fs.cursor] + insert_ch + fs.buffer[fs.cursor :]
            fs.cursor += 1
            return

    def _set_status(self, status: str) -> None:
        """Wrap core.ops.set_status with error handling and reload."""
        task = self._current_task()
        if task is None:
            self.state.msg_footer = "No task selected"
            return

        try:
            set_status(task.id, status)  # type: ignore[arg-type]
        except OpsError as e:
            self.state.msg_footer = f"Error: {e}"
        else:
            self.state.msg_footer = f"Status -> {status}: {task.id[:6]:<6}"
            self._reload_tasks(keep_task_id=task.id)

    def _toggle_archive_tree(self, *, archive: bool) -> None:
        """Archive or unarchive weakly connected component."""
        task = self._current_task()
        if task is None:
            self.state.msg_footer = "No task selected"
            return

        try:
            if archive:
                changed = archive_tree(task.id)
                action = "archived"
            else:
                changed = unarchive_tree(task.id)
                action = "unarchived"
        except OpsError as e:
            self.state.msg_footer = f"Error: {e}"
        else:
            if changed:
                self.state.msg_footer = f"{action}: {len(changed)} task(s)"
            else:
                self.state.msg_footer = f"No tasks {action}"
            # archive フィルタの有無で一覧に残るかどうかは変わるので、
            # keep_task_id はとりあえず指定しない
            self._reload_tasks()

    # ---- filter helpers -------------------------------------------------

    def _cycle_status_filter(self, *, reverse: bool = False) -> None:
        """Cycle status filter: all -> pending -> in_prog -> done -> requested -> all."""
        order: list[str | None] = [None, "pending", "in_progress", "done", "requested"]
        current = self.state.filter.status
        try:
            idx = order.index(current)
        except ValueError:
            idx = 0
        idx = (idx + 1) % len(order) if not reverse else (idx - 1) % len(order)
        self.state.filter.status = order[idx]

        label_map = {
            None: "all",
            "pending": "pending",
            "in_progress": "in_prog",
            "done": "done",
            "requested": "requested",
        }
        label = label_map.get(self.state.filter.status, "all")
        self.state.msg_footer = f"Filter: status={label}"
        self._reload_tasks()

    def _cycle_archived_filter(self) -> None:
        """Cycle archived filter: active -> archived -> all -> active."""
        order: list[bool | None] = [False, True, None]
        current = self.state.filter.archived
        try:
            idx = order.index(current)
        except ValueError:
            idx = 0
        idx = (idx + 1) % len(order)
        self.state.filter.archived = order[idx]

        if self.state.filter.archived is True:
            label = "archived"
        elif self.state.filter.archived is False:
            label = "active"
        else:
            label = "all"

        self.state.msg_footer = f"Filter: archived={label}"
        self._reload_tasks()

    def _toggle_requested_only_filter(self) -> None:
        """Toggle requested_only filter."""
        self.state.filter.requested_only = not self.state.filter.requested_only
        label = "on" if self.state.filter.requested_only else "off"
        self.state.msg_footer = f"Filter: requested_only={label}"
        self._reload_tasks()

    def _toggle_topo(self) -> None:
        """Toggle topo ordering."""
        self.state.filter.topo = not self.state.filter.topo
        label = "on" if self.state.filter.topo else "off"
        self.state.msg_footer = f"Topo={label}"
        self._reload_tasks()

    def handle_key(self, key: int, ch: str | None = None) -> bool:  # noqa: C901
        # in dialog
        if self.state.mode == "dialog" and self.state.dialog is not None:
            self._handle_dialog_key(key, ch)
            return True

        # in overlay
        if self.state.mode == "overlay" and self.state.overlay is not None:
            self._handle_overlay_key(key)
            return True

        # key に応じて state を更新し、必要なら ops を呼ぶ
        # True を返したら継続、False ならループ終了
        if key in (ord("q"), ord("Q")):
            return False
        # ダミー行でのEnter
        if key in (curses.KEY_ENTER, 10, 13) and self.state.selected_index == 0:
            # add new task
            self._start_add_dialog()
            return True

        # move up/down
        if key in (curses.KEY_UP,) and self.state.selected_index > 0:
            self.state.selected_index -= 1
            self.state.detail_offset = 0
        elif key in (curses.KEY_DOWN,) and self.state.selected_index < len(self.state.tasks):
            self.state.selected_index += 1
            self.state.detail_offset = 0
        elif key in (curses.KEY_HOME,):
            self.state.selected_index = 0
            self.state.detail_offset = 0
        elif key in (curses.KEY_END,):
            self.state.selected_index = len(self.state.tasks)
            self.state.detail_offset = 0
        elif key in (curses.KEY_PPAGE,):
            self.state.selected_index -= self.state.window_list_height
            self.state.detail_offset = 0
        elif key in (curses.KEY_NPAGE,):
            self.state.selected_index += self.state.window_list_height
            self.state.detail_offset = 0

        # shortcut keys
        elif key in (ord("f"),):
            # status filter cycle
            self._cycle_status_filter()
        elif key in (ord("F"),):
            # status filter cycle
            self._cycle_status_filter(reverse=True)
        elif key in (ord("a"),):
            # archived filter cycle
            self._cycle_archived_filter()
        elif key in (ord("r"),):
            # requested_only toggle
            self._toggle_requested_only_filter()
        elif key in (ord("t"),):
            # topo on/off
            self._toggle_topo()
        elif key in (ord("p"),):
            # pending
            self._set_status("pending")
        elif key in (ord("i"),):
            # in_progress
            self._set_status("in_progress")
        elif key in (ord("d"),):
            # done
            self._set_status("done")
        elif key in (ord("x"),):
            # archive tree
            self._toggle_archive_tree(archive=True)
        elif key in (ord("u"),):
            # unarchive tree
            self._toggle_archive_tree(archive=False)

        # scroll keys
        elif key in (ord("["),):
            self._scroll_detail(-1)
        elif key in (ord("]"),):
            self._scroll_detail(+1)

        # dialog keys
        elif key in (ord("A"),):
            # add new task
            self._start_add_dialog()
        elif key in (ord("E"),):
            # edit current task
            self._start_edit_dialog()
        elif key in (ord("R"),):
            # requested
            self._start_request_dialog()
        elif key in (ord("G"),):
            # graph overlay
            self._start_graph_overlay()
        return True


def main(stdscr: curses.window, args: argparse.Namespace | None = None) -> int:
    app = App(stdscr, args)
    while True:
        app.draw()
        key_raw = stdscr.get_wch()
        key = ord(key_raw) if isinstance(key_raw, str) else key_raw
        ch = key_raw if isinstance(key_raw, str) else None
        cont = app.handle_key(key, ch)
        if not cont:
            break
    return 0


def run(args: argparse.Namespace | None = None) -> int:
    return curses.wrapper(main, args)
