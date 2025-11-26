import argparse
import curses
import locale
from collections.abc import Callable
from datetime import datetime
from typing import TypeVar

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
from dandori.interfaces.tui.data import AppState, DialogState, FieldState, OverlayState
from dandori.interfaces.tui.style import LENGTH_SHORTEND_ID
from dandori.interfaces.tui.view import AppView
from dandori.util.ids import parse_ids_with_msg
from dandori.util.logger import setup_logger

logger = setup_logger("dandori", is_stream=True, is_file=True)

locale.setlocale(locale.LC_ALL, "")

T = TypeVar("T")
V = TypeVar("V")


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

MAX_DIALOG_BOX_WIDTH = 80
MAX_OVERLAY_BOX_WIDTH = 100


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
        help_line += "[(p)end] [(i)n_progress] [(d)one] [(x)Archive] [(u)narchive] [(q)uit]"
        return help_line


class App:
    def __init__(
        self,
        stdscr: curses.window,
        args: argparse.Namespace | None = None,
    ) -> None:
        self.stdscr = stdscr
        self.args = args
        self.state = AppState()
        self.view = AppView(stdscr, self.state)
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

    # ---- overlay helpers ------------------------------------------------

    def _start_graph_overlay(self) -> None:
        """Show local graph (deps and children) for current task."""
        task = self.view.current_task()
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
                s += f"({d.id[:LENGTH_SHORTEND_ID].ljust(LENGTH_SHORTEND_ID)}) "
                s += f"{d.title} "
                s += f"[{d.due_date}]" if d.due_date else ""
                lines.append(s)
        else:
            lines.append("  ^")
        # ---
        lines.append("(Selected)")
        s = f"  - [{STATUS_MARK_MAP.get(task.status, '?')}] "
        s += f"({task.id[:LENGTH_SHORTEND_ID].ljust(LENGTH_SHORTEND_ID)}) "
        s += f"{task.title} "
        s += f"[{task.due_date}]" if task.due_date else ""
        lines.append(s)
        # ---
        lines.append("(Depended by)")
        if children:
            for c in children:
                s = f"  v [{STATUS_MARK_MAP.get(c.status, '?')}] "
                s += f"({c.id[:LENGTH_SHORTEND_ID].ljust(LENGTH_SHORTEND_ID)}) "
                s += f"{c.title} "
                s += f"[{c.due_date}]" if c.due_date else ""
                lines.append(s)
        else:
            lines.append("  v")
        # ---
        lines.append("-" * 12)  # 12は"Depended by:"の長さ

        self.state.overlay = OverlayState(
            title="Local graph",
            lines=lines,
        )
        self.state.overlay_offset = 0
        self.state.mode = "overlay"

    def _handle_overlay_key(self, key: int) -> None:
        """Handle key press in overlay mode (scrolling and closing)."""
        ov = self.state.overlay
        # ESC: close
        if ov is None or len(ov.lines) < 1 or key in (27,):
            self.state.mode = "list"
            self.state.overlay = None
            self.state.overlay_offset = 0
            return

        # 可視行数を計算
        max_y, _ = self.stdscr.getmaxyx()
        header_height = HeaderLines.height()
        footer_height = 1
        content_height = max_y - header_height - footer_height
        total_lines = len(ov.lines)
        max_box_height = content_height
        raw_height = min(total_lines + 2, max_box_height)
        box_height = min(raw_height, max_box_height)
        lines_rows = max(1, box_height - 2)

        max_offset = max(0, total_lines - lines_rows)
        offset = self.state.overlay_offset

        if key in (curses.KEY_UP,):
            offset = max(0, offset - 1)
        elif key in (curses.KEY_DOWN,):
            offset = min(max_offset, offset + 1)
        elif key in (curses.KEY_HOME,):
            offset = 0
        elif key in (curses.KEY_END,):
            offset = max_offset
        elif key in (curses.KEY_PPAGE,):
            offset = max(0, offset - lines_rows)
        elif key in (curses.KEY_NPAGE,):
            offset = min(max_offset, offset + lines_rows)
        else:
            # ignore other keys
            return
        self.state.overlay_offset = offset

    # ---- small helpers --------------------------------------------------

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
        self.state.dialog_offset = 0
        self.state.mode = "dialog"

    def _start_edit_dialog(self) -> None:
        """Open dialog to edit the current task"""
        task = self.view.current_task()
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
                buffer=task.start_at or "",
                cursor=len(task.start_at or ""),
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
                label=f"Depends on ({LENGTH_SHORTEND_ID}-chars, ',')  ",
                buffer=", ".join([t[:LENGTH_SHORTEND_ID] for t in task.depends_on]),
                cursor=len(", ".join([t[:LENGTH_SHORTEND_ID] for t in task.depends_on])),
            ),
            FieldState(
                name="children",
                label=f"Children ({LENGTH_SHORTEND_ID}-chars, ',')    ",
                buffer=", ".join([t[:LENGTH_SHORTEND_ID] for t in task.children]),
                cursor=len(", ".join([t[:LENGTH_SHORTEND_ID] for t in task.children])),
            ),
        ]
        self.state.dialog = DialogState(
            kind="edit",
            title="Edit Task",
            fields=fields,
            current_index=0,
            target_task_id=task.id,
        )
        self.state.dialog_offset = 0
        self.state.mode = "dialog"

    def _start_request_dialog(self) -> None:
        """Open dialog to mark current task as requested (assignee + note)"""
        task = self.view.current_task()
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
        self.state.dialog_offset = 0
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

    def _apply_dialog(self) -> None:  # noqa: C901
        """Apply the dialog result (add/edit)"""
        dlg = self.state.dialog
        if dlg is None:
            return
        # フィールドをdictにまとめる
        values: dict[str, str] = {f.name: f.buffer.strip() for f in dlg.fields}
        try:
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
                lambda s: parse_ids_with_msg(
                    s,
                    source_ids=[t.id for t in self.state.tasks],
                    msg_buffer=self.state.msg_footer,
                    shortend_length=LENGTH_SHORTEND_ID,
                ),
                None,
                "Invalid depends_on value '{}'",
            )
            # children (optional)
            children = self._parse_field(
                values,
                "children",
                lambda s: parse_ids_with_msg(
                    s,
                    source_ids=[t.id for t in self.state.tasks],
                    msg_buffer=self.state.msg_footer,
                    shortend_length=LENGTH_SHORTEND_ID,
                ),
                None,
                "Invalid children value '{}'",
            )
        except Exception as err:  # noqa: BLE001
            self.state.msg_footer = f"Error (apply_dialog): {err}"
            return

        # add task
        if dlg.kind == "add":
            # title (required)
            if (title := values.get("title")) is None:
                self.state.msg_footer = "Empty title: canceled"
                return
            # 親は「現在選択中のタスク」で、なければルートタスク
            parent_ids: list[str] = []
            current = self.view.current_task()
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
                self.state.msg_footer = f"Added: {task.id[:LENGTH_SHORTEND_ID].ljust(LENGTH_SHORTEND_ID)}"
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
                self.state.msg_footer = f"Updated: {task.id[:LENGTH_SHORTEND_ID].ljust(LENGTH_SHORTEND_ID)}"
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
                self.state.msg_footer = (
                    f"Requested: {dlg.target_task_id[:LENGTH_SHORTEND_ID].ljust(LENGTH_SHORTEND_ID)}"
                )
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
            fs.cursor += len(insert_ch)
            return

    def _set_status(self, status: str) -> None:
        """Wrap core.ops.set_status with error handling and reload."""
        task = self.view.current_task()
        if task is None:
            self.state.msg_footer = "No task selected"
            return

        try:
            set_status(task.id, status)  # type: ignore[arg-type]
        except OpsError as e:
            self.state.msg_footer = f"Error: {e}"
        else:
            self.state.msg_footer = f"Status -> {status}: {task.id[:LENGTH_SHORTEND_ID].ljust(LENGTH_SHORTEND_ID)}"
            self._reload_tasks(keep_task_id=task.id)

    def _toggle_archive_tree(self, *, archive: bool) -> None:
        """Archive or unarchive weakly connected component."""
        task = self.view.current_task()
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

        # change sort order of filter
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

        # change status
        elif key in (ord("P"),):
            # pending
            self._set_status("pending")
        elif key in (ord("I"),):
            # in_progress
            self._set_status("in_progress")
        elif key in (ord("D"),):
            # done
            self._set_status("done")
        elif key in (ord("X"),):
            # archive tree
            self._toggle_archive_tree(archive=True)
        elif key in (ord("U"),):
            # unarchive tree
            self._toggle_archive_tree(archive=False)

        # scroll keys
        elif key in (ord("["),):
            self.view.scroll_detail(-1)
        elif key in (ord("]"),):
            self.view.scroll_detail(+1)

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
