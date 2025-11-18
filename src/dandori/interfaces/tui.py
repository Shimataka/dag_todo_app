import argparse
import curses
import locale
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from dandori.core.models import Task
from dandori.core.ops import (
    OpsError,
    add_task,
    archive_tree,
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

Mode = Literal[
    "list",
    "dialog",
]
DialogKind = Literal[
    "add",
    "edit",
    "request",
]

HEADER_TITLE = "dandori TUI  "
HEADER_TITLE += "[↑/↓, (q)uit, (a)dd, (e)dit, (p)ending, (i)n_progress, (d)one, (r)equested, (x)archive, (u)narchive]"


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

    # UI用
    message: str | None = None  # フッターメッセージ表示
    show_help: bool = False  # [h]キーでヘルプ表示トグル


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

    def _init_curses(self) -> None:
        # 色やキーパッドの設定で、画面サイズ対応もあればここ。
        curses.curs_set(0)
        self.stdscr.keypad(True)  # noqa: FBT003

        if curses.has_colors():
            curses.start_color()
            curses.use_default_colors()
            # color pair indexes
            curses.init_pair(1, curses.COLOR_CYAN, -1)  # header
            curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_WHITE)  # selected row
            curses.init_pair(3, curses.COLOR_MAGENTA, -1)  # archived
            curses.init_pair(4, curses.COLOR_GREEN, -1)  # done/requested

    def _reload_tasks(self, keep_task_id: str | None = None) -> None:
        """Reload tasks from backend according to filter."""
        # FilterState に基づいて core.ops.list_tasks() を呼んで state.tasks を更新
        self.state.tasks = list_tasks(
            status=self.state.filter.status,  # type: ignore[arg-type]
            archived=self.state.filter.archived,
            topo=self.state.filter.topo,
            requested_only=self.state.filter.requested_only,
        )

        # clamp selection index
        if not self.state.tasks:
            self.state.selected_index = 0
        else:
            self.state.selected_index = max(
                0,
                min(self.state.selected_index, len(self.state.tasks) - 1),
            )

        # clamp / restore selection index
        if not self.state.tasks:
            self.state.selected_index = 0
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

    def _safe_addnstr(self, y: int, x: int, s: str, n: int) -> None:
        max_y, max_x = self.stdscr.getmaxyx()
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

        header_height = 1
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

        self.stdscr.refresh()

    def _draw_header(self, y: int, width: int) -> None:
        title = HEADER_TITLE
        if curses.has_colors():
            self.stdscr.attron(curses.color_pair(1))
        self._safe_addnstr(y, 0, title.ljust(width), width)
        if curses.has_colors():
            self.stdscr.attroff(curses.color_pair(1))

    def _draw_footer(self, y: int, width: int) -> None:
        msg = self.state.message or ""
        if curses.has_colors():
            self.stdscr.attron(0)
        self._safe_addnstr(y, 0, msg.ljust(width), width)
        if curses.has_colors():
            self.stdscr.attroff(0)

    def _draw_list(self, y: int, height: int, width: int) -> None:
        tasks = self.state.tasks
        rows_to_draw = min(height, len(tasks))
        for idx in range(rows_to_draw):
            row_y = y + idx
            attrs = 0
            if idx == self.state.selected_index:
                if curses.has_colors():
                    attrs |= curses.color_pair(2)
                attrs |= curses.A_REVERSE
            if attrs:
                self.stdscr.attron(attrs)
            if idx == 0:
                line = "[--- Add a task ---]"
                self._safe_addnstr(row_y, 0, line.ljust(width), width)
            else:
                t = tasks[idx - 1]
                line = self._format_list_line(t, width)
                self._safe_addnstr(row_y, 0, line.ljust(width), width)
            if attrs:
                self.stdscr.attroff(attrs)

    def _format_list_line(self, t: Task, width: int) -> str:
        # status/archived marks
        marks: list[str] = []
        if t.is_archived:
            marks.append("A")
        # elif t.status == "pending":
        #     marks.append("P")
        elif t.status == "requested":
            marks.append("R")
        elif t.status == "in_progress":
            marks.append("I")
        elif t.status == "done":
            marks.append("D")
        status_str = "".join(marks) or "-"

        short_id = t.id[:6]
        title = t.title.replace("\n", " ")

        line = f"{status_str} {short_id} {title}"
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

        lines = self._draw_detail_lines(t)
        row = 0
        for line in lines:
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

    def _draw_detail_lines(self, t: Task) -> list[str]:
        lines: list[str] = []
        lines.append(f"ID: {t.id}")
        lines.append(f"Title       : {t.title}")
        status: str = t.status
        if t.is_archived:
            status += " (archived)"
        lines.append(f"Status      : {status}")
        lines.append(f"Priority    : {t.priority}")
        lines.append(f"Start       : {t.start_date or ''}")
        lines.append(f"Due         : {t.due_date or ''}")
        lines.append("Request")
        lines.append(f"  - to      : {t.assigned_to or ''}")
        lines.append(f"  - at      : {t.requested_at or ''}")
        lines.append(f"  - by      : {t.requested_by or ''}")
        n_ = t.requested_note or "[No note]"
        lines.append(f"  - note    : {n_}")
        lines.append("Tags        : ")
        lines.extend(["  - " + tag for tag in t.tags])
        lines.append("Depends on  : ")
        lines.extend(["  - " + dep for dep in t.depends_on])
        lines.append("Children    :   ")
        lines.extend(["  - " + child for child in t.children])
        d_ = t.description or "[No description]"
        lines.append(f"Description : {d_}")
        return lines

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

    # ---- small helpers --------------------------------------------------

    def _current_task(self) -> Task | None:
        """Return currently selected task or None."""
        if not self.state.tasks:
            return None
        # index 0 はルートタスク追加用のダミー行として扱う
        idx = self.state.selected_index
        if idx <= 0:
            return None
        real_idx = idx - 1
        if not (0 <= real_idx < len(self.state.tasks)):
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
            self.state.message = "No task selected"
            return
        fields = [
            FieldState(
                name="title",
                label="Title                   ",
                buffer=task.title,
                cursor=len(task.title),
            ),
            FieldState(
                name="priority",
                label="Priority (0-9)          ",
                buffer=str(task.priority),
                cursor=len(str(task.priority)),
            ),
            FieldState(
                name="start_date",
                label="Start Date (ISO format) ",
                buffer=task.start_date or "",
                cursor=len(task.start_date or ""),
            ),
            FieldState(
                name="due_date",
                label="Due Date (ISO format)   ",
                buffer=task.due_date or "",
                cursor=len(task.due_date or ""),
            ),
            FieldState(
                name="tags",
                label="Tags (',' separated)    ",
                buffer=", ".join(task.tags),
                cursor=len(", ".join(task.tags)),
            ),
            FieldState(
                name="description",
                label="Description             ",
                buffer=task.description,
                cursor=len(task.description),
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
            self.state.message = "No task selected"
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

    def _apply_dialog(self) -> None:  # noqa: C901
        """Apply the dialog result (add/edit)"""
        dlg = self.state.dialog
        if dlg is None:
            return
        # フィールドをdictにまとめる
        values: dict[str, str] = {f.name: f.buffer.strip() for f in dlg.fields}
        # priority (optional)
        if (_priority := values.get("priority")) is not None and _priority != "":
            try:
                priority = int(_priority)
            except ValueError:
                self.state.message = f"Invalid priority value '{_priority}': canceled"
                return
        else:
            priority = 0
        # start_date (optional)
        if (_start_date := values.get("start_date")) is not None and _start_date != "":
            try:
                start_date = datetime.fromisoformat(_start_date)
            except ValueError:
                self.state.message = f"Invalid start date value '{_start_date}': canceled"
                return
        else:
            start_date = None
        # due_date (optional)
        if (_due_date := values.get("due_date")) is not None and _due_date != "":
            try:
                due_date = datetime.fromisoformat(_due_date)
            except ValueError:
                self.state.message = f"Invalid due date value '{_due_date}': canceled"
                return
        else:
            due_date = None
        # tags (optional)
        tags = _tags.split(",") if (_tags := values.get("tags")) else None
        # assignee (optional)
        assignee = values.get("assignee")
        # note (optional)
        note = values.get("note")

        # add task
        if dlg.kind == "add":
            # title (required)
            if (title := values.get("title")) is None:
                self.state.message = "Empty title: canceled"
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
                self.state.message = f"Error (add): {e}"
                return
            else:
                self.state.message = f"Added: {task.id[:6]}"
                self._reload_tasks(keep_task_id=task.id)
        # edit task
        elif dlg.kind == "edit":
            # title (required)
            if (title := values.get("title")) is None:
                self.state.message = "Empty title: canceled"
                return
            if dlg.target_task_id is None:
                self.state.message = "No task selected for edit"
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
                )
            except OpsError as e:
                self.state.message = f"Error (edit): {e}"
                return
            else:
                self.state.message = f"Updated: {task.id[:6]}"
                self._reload_tasks(keep_task_id=task.id)
        elif dlg.kind == "request":
            # title (required)
            if dlg.target_task_id is None:
                self.state.message = "No task selected for request"
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
                self.state.message = f"Error (request): {e}"
                return
            else:
                self.state.message = f"Requested: {dlg.target_task_id[:6]}"
                self._reload_tasks(keep_task_id=dlg.target_task_id)

        else:
            _msg = f"Invalid dialog kind: {dlg.kind}"  # type: ignore[unreachable]
            logger.error(_msg)
            self.state.message = _msg
            return

    def _handle_dialog_key(self, key: int) -> None:  # noqa: C901
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
            self.state.message = "Canceled"
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

        # Backspace: delete char
        if key in (curses.KEY_BACKSPACE, 127, 8):
            if fs.cursor > 0:
                fs.buffer = fs.buffer[: fs.cursor - 1] + fs.buffer[fs.cursor :]
                fs.cursor -= 1
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
        if 32 <= key <= 126:
            ch = chr(key)
            fs.buffer = fs.buffer[: fs.cursor] + ch + fs.buffer[fs.cursor :]
            fs.cursor += 1
            return

    def _set_status(self, status: str) -> None:
        """Wrap core.ops.set_status with error handling and reload."""
        task = self._current_task()
        if task is None:
            self.state.message = "No task selected"
            return

        try:
            set_status(task.id, status)  # type: ignore[arg-type]
        except OpsError as e:
            self.state.message = f"Error: {e}"
        else:
            self.state.message = f"Status -> {status}: {task.id[:6]}"
            self._reload_tasks(keep_task_id=task.id)

    def _toggle_archive_tree(self, *, archive: bool) -> None:
        """Archive or unarchive weakly connected component."""
        task = self._current_task()
        if task is None:
            self.state.message = "No task selected"
            return

        try:
            if archive:
                changed = archive_tree(task.id)
                action = "archived"
            else:
                changed = unarchive_tree(task.id)
                action = "unarchived"
        except OpsError as e:
            self.state.message = f"Error: {e}"
        else:
            if changed:
                self.state.message = f"{action}: {len(changed)} task(s)"
            else:
                self.state.message = f"No tasks {action}"
            # archive フィルタの有無で一覧に残るかどうかは変わるので、
            # keep_task_id はとりあえず指定しない
            self._reload_tasks()

    def handle_key(self, key: int) -> bool:  # noqa: C901
        # in dialog
        if self.state.mode == "dialog" and self.state.dialog is not None:
            self._handle_dialog_key(key)
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

        if key in (curses.KEY_UP,) and self.state.selected_index > 0:
            self.state.selected_index -= 1
        elif key in (curses.KEY_DOWN,) and self.state.selected_index < len(self.state.tasks):
            self.state.selected_index += 1
        elif key in (ord("a"), ord("A")):
            # add new task
            self._start_add_dialog()
        elif key in (ord("e"), ord("E")):
            # edit current task
            self._start_edit_dialog()
        elif key in (ord("p"), ord("P")):
            # pending
            self._set_status("pending")
        elif key in (ord("i"), ord("I")):
            # in_progress
            self._set_status("in_progress")
        elif key in (ord("d"), ord("D")):
            # done
            self._set_status("done")
        elif key in (ord("r"), ord("R")):
            # requested (簡易版: 詳細入力は Step3 で対応)
            self._start_request_dialog()
        elif key in (ord("x"), ord("X")):
            # archive tree
            self._toggle_archive_tree(archive=True)
        elif key in (ord("u"), ord("U")):
            # unarchive tree
            self._toggle_archive_tree(archive=False)
        return True


def main(stdscr: curses.window, args: argparse.Namespace | None = None) -> int:
    app = App(stdscr, args)
    while True:
        app.draw()
        key = stdscr.getch()
        cont = app.handle_key(key)
        if not cont:
            break
    return 0


def run(args: argparse.Namespace | None = None) -> int:
    return curses.wrapper(main, args)
