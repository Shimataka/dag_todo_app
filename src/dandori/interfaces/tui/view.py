import curses
import locale
from dataclasses import dataclass

from dandori.core.models import Task
from dandori.interfaces.tui.data import AppState
from dandori.interfaces.tui.helper import _string_width
from dandori.interfaces.tui.style import (
    ADD_TASK_COLOR,
    COMPLETED_COLOR,
    DIALOG_BG_COLOR,
    LENGTH_SHORTEND_ID,
    MAIN_THEME_COLOR,
    MAX_DIALOG_BOX_WIDTH,
    MAX_OVERLAY_BOX_WIDTH,
    OVERLAY_BG_COLOR,
    REQUESTED_COLOR,
    STATUS_MARK_MAP,
    SURPRESSED_COLOR,
    WAITING_COLOR,
    WORKING_COLOR,
    HeaderLines,
)
from dandori.util.logger import setup_logger

logger = setup_logger("dandori", is_stream=True, is_file=True)

locale.setlocale(locale.LC_ALL, "")


@dataclass
class AppView:
    """AppView class to draw overall app screen.

    Attributes:
        stdscr: curses.window
        state: AppState
    """

    stdscr: curses.window
    state: AppState

    def draw(self) -> None:
        """Draw overall app screen."""
        self.stdscr.erase()
        max_y, max_x = self.stdscr.getmaxyx()
        if max_y < 2 or max_x < 2:
            # give up drawing if terminal size is too small
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

        # header/fotter
        self._draw_header(0, max_x)
        self._draw_footer(max_y - 1, max_x)

        # main
        self._draw_list(header_height, content_height, list_width)
        self._draw_detail(header_height, content_height, list_width, detail_width)

        # dialog
        if self.state.mode == "dialog" and self.state.dialog is not None:
            self._draw_dialog(header_height, content_height, max_x)
        else:
            # hide cursor if not in dialog
            try:
                self._cursor_off()
            except curses.error:
                logger.exception("Error (cursor off)")
                self.state.msg_footer = "Error (cursor off)"

        # overlay
        if self.state.mode == "overlay" and self.state.overlay is not None:
            self._draw_overlay(header_height, content_height, max_x)

        self.stdscr.refresh()

    def scroll_detail(self, delta: int) -> None:
        """Scroll detail view by delta visual lines."""
        if delta == 0:
            return

        task = self.current_task()
        if task is None:
            return

        max_y, max_x = self.stdscr.getmaxyx()
        header_height = HeaderLines.height()
        footer_height = 1
        content_height = max_y - header_height - footer_height
        if content_height <= 0 or max_x <= 0:
            return

        list_width = max_x // 2
        detail_width = max_x - list_width

        visual_lines = self._build_detail_lines(task, detail_width)
        if not visual_lines:
            return

        max_offset = max(0, len(visual_lines) - max(0, content_height))
        new_offset = self.state.detail_offset + delta
        self.state.detail_offset = max(0, min(new_offset, max_offset))

    def _safe_addnstr(self, y: int, x: int, s: str, n: int) -> None:
        """Add a string to the screen safely."""
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

    # header/footer
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

        # requested only表示
        req_label = "on" if f.requested_only else "off"

        # ready only表示
        ready_label = "on" if f.ready_only else "off"

        # topo表示
        topo_label = "on" if f.topo else "off"

        # bottleneck only表示
        bottleneck_label = "on" if f.bottleneck_only else "off"

        # component表示
        component_label = (
            "all"
            if f.component_task_id is None
            else f.component_task_id[:LENGTH_SHORTEND_ID].ljust(LENGTH_SHORTEND_ID)
        )

        title = HeaderLines.title()
        status = HeaderLines.status(
            status_label,
            archived_label,
            topo_label,
            req_label,
            ready_label,
            bottleneck_label,
            component_label,
        )
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

    # list view
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

        self.state.list_offset = max(
            0,
            min(self.state.list_offset, max(0, total_rows - height)),
        )

        start = self.state.list_offset
        end = min(start + height, total_rows)

        for i, idx in enumerate[int](range(start, end)):
            try:
                t = tasks[idx - 1]
            except IndexError:
                t = Task(
                    id="Unknown",
                    owner="Unknown",
                    title=f"IndexError with idx={idx - 1}",
                )
            row_y = y + i

            attrs = 0
            if curses.has_colors():
                # color on
                if idx == 0:
                    attrs |= curses.color_pair(ADD_TASK_COLOR)
                # done
                elif t.status == "done":
                    attrs |= curses.color_pair(COMPLETED_COLOR)
                # requested
                elif t.status == "requested":
                    attrs |= curses.color_pair(REQUESTED_COLOR)
                # in_progress
                elif t.status == "in_progress":
                    attrs |= curses.color_pair(WORKING_COLOR)
                # pending
                elif t.status == "pending":
                    attrs |= curses.color_pair(WAITING_COLOR)
                # removed
                elif t.is_archived:
                    attrs |= curses.color_pair(SURPRESSED_COLOR)

                # selected
                if idx == self.state.selected_index:
                    attrs |= curses.A_REVERSE

                if attrs:
                    self.stdscr.attron(attrs)

            # draw
            if idx == 0:
                line = "[+] Add Task (press Enter or 'A' key)"
                self._safe_addnstr(row_y, 0, line.ljust(width), width)
            else:
                line = self._format_list_line(t, width)
                self._safe_addnstr(row_y, 0, line.ljust(width), width)

            if attrs:
                self.stdscr.attroff(attrs)

        # clear residual rows
        for i in range(end - start, height):
            row_y = y + i
            if curses.has_colors():
                self.stdscr.attron(0)
            self._safe_addnstr(row_y, 0, " " * width, width)
            if curses.has_colors():
                self.stdscr.attroff(0)

    def _format_list_line(self, t: Task, width: int) -> str:
        # status / archived marks
        marks: list[str] = []
        if t.is_archived:
            marks.append("A")
        status_str = STATUS_MARK_MAP.get(t.status, "-")

        short_id = t.id[:LENGTH_SHORTEND_ID]
        title = t.title.replace("\n", "")

        line = f"{status_str} {short_id.ljust(LENGTH_SHORTEND_ID)} {title}"
        return line[:width]

    # detail view
    def _draw_detail(  # noqa: C901
        self,
        y: int,
        height: int,
        x: int,
        width: int,
    ) -> None:
        if height <= 0 or width <= 0:
            return

        # clear background
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

        t = self.current_task()
        if t is None:
            return

        visual_lines = self._build_detail_lines(t, width)
        if not visual_lines:
            visual_lines = ["(no details)"]

        # clamp detail_offset
        max_offset = max(0, len(visual_lines) - max(0, height))
        self.state.detail_offset = max(0, min(self.state.detail_offset, max_offset))

        start = self.state.detail_offset
        end = min(start + height, len(visual_lines))

        row = 0
        for line in visual_lines[start:end]:
            if row >= height:
                break
            start_idx = 0
            while start_idx < len(line) and row < height:
                chunk = line[start_idx : start_idx + width]
                if curses.has_colors():
                    self.stdscr.attron(0)
                self._safe_addnstr(y + row, x, chunk, width)
                if curses.has_colors():
                    self.stdscr.attroff(0)
                start_idx += width
                row += 1

    def _build_detail_lines(
        self,
        t: Task,
        width: int,
    ) -> list[str]:
        """Build wrapped detail lines for a task.

        Args:
            t: Task
            width: int

        Returns:
            list[str]: wrapped detail lines
        """
        base: list[str] = []
        base.append(f"ID      : {t.id[:LENGTH_SHORTEND_ID]}")
        base.append(f"Full-ID : {t.id}")
        base.append(f"Title   : {t.title}")
        base.append(f"Owner   : {t.owner}")
        status: str = t.status
        if t.is_archived:
            status += " (archived)"
        base.append(f"Status  : {status}")
        base.append(f"Priority: {t.priority}")
        base.append(f"Start   : {t.start_at or ''}")
        base.append(f"Due     : {t.due_date or ''}")
        base.append(f"Done    : {t.done_at or ''}")
        base.append(f"REQ at  : {t.requested_at or ''}")
        base.append(f"REQ by  : {t.requested_by or ''}")
        base.append(f"REQ note: {t.requested_note or ''}")
        base.append(f"Assgn to: {t.assigned_to or ''}")
        base.append("Tags    : " + ", ".join(t.tags))
        base.append(
            "Parents : " + ", ".join([s[:LENGTH_SHORTEND_ID] for s in t.depends_on]),
        )
        base.append(
            "Children: "
            + ", ".join(
                [s[:LENGTH_SHORTEND_ID] for s in t.children],
            ),
        )
        base.append(f"DESC    : {t.description}")

        # wrap lines
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

    # dialog
    def _draw_dialog(  # noqa: C901
        self,
        content_y: int,
        content_height: int,
        max_x: int,
    ) -> None:
        """Draw dialog content.

        Args:
            content_y: int
            content_height: int
            max_x: int
        """
        dlg = self.state.dialog
        if dlg is None:
            return

        num_fields = len(dlg.fields)
        if num_fields == 0:
            return

        box_width = min(MAX_DIALOG_BOX_WIDTH, max_x - 4)
        max_box_height = content_height
        # title(1) + empty(1) + fields(num_fields) + hint(1)
        raw_height = 3 + num_fields
        box_height = min(raw_height, max_box_height)
        # フィールドを描画できる行数
        field_rows = max(1, max_box_height - 3)

        # スクロールオフセットの調整
        offset = self.state.dialog_offset
        max_offset = max(0, num_fields - field_rows)
        offset = max(0, min(offset, max_offset))

        # 現在のフィールドが可視範囲に入るように調整
        if dlg.current_index < offset:
            offset = dlg.current_index
        elif dlg.current_index >= offset + field_rows:
            offset = dlg.current_index - field_rows + 1
        self.state.dialog_offset = offset

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

        # フィールド群 (スクロール対応)
        max_label_width = 18
        max_input_width = box_width - max_label_width
        row = top + 2
        end_index = min(offset + field_rows, num_fields)
        for idx in range(offset, end_index):
            fs = dlg.fields[idx]
            marker = ">" if idx == dlg.current_index else " "
            label = f"{marker} {fs.label}: "
            value = fs.buffer
            # show last part if input overflows
            if len(value) > max_input_width:
                value = value[-max_input_width:]
            line = (label + value)[:box_width]
            self._safe_addnstr(row, left, line.ljust(box_width), box_width)
            row += 1

        # ヒント
        hint = "[Tab/↑/↓: Move, Enter: Apply, Esc: Cancel]"
        self._safe_addnstr(top + box_height - 1, left, hint.ljust(box_width), box_width)

        # ---- draw text cursor ---------------------------------------------
        try:
            if 0 <= dlg.current_index < num_fields:
                fs = dlg.fields[dlg.current_index]
                # calculate cursor position
                cursor_row = top + 2 + dlg.current_index - offset
                # label + marker + space
                label = f"> {fs.label}: "
                # input field start position = left + label width
                cursor_col = left + _string_width(label)
                # buffer position = cursor position + buffer content before cursor
                cursor_col += _string_width(fs.buffer[: fs.cursor])
                # move physical cursor
                curses.curs_set(1)
                max_y, max_x2 = self.stdscr.getmaxyx()
                if 0 <= cursor_row < max_y and 0 <= cursor_col < max_x2:
                    self.stdscr.move(cursor_row, cursor_col)
                else:
                    _msg = f"Cursor position out of screen: row={cursor_row}, col={cursor_col}"
                    logger.warning(_msg)
        except IndexError:
            # cursor control may be failed depending on the terminal environment
            _msg = f"Current index out of range: {dlg.current_index}"
            logger.warning(_msg)
        finally:
            if curses.has_colors() and attr:
                self.stdscr.attroff(attr)

    def _draw_overlay(
        self,
        content_y: int,
        content_height: int,
        max_x: int,
    ) -> None:
        """Draw overlay content.

        Args:
            content_y: int
            content_height: int
            max_x: int
        """
        ovl = self.state.overlay
        if ovl is None or not ovl.lines:
            return

        # bg color on
        attr = 0
        if curses.has_colors():
            attr |= curses.color_pair(OVERLAY_BG_COLOR)
        self.stdscr.attron(attr)

        # row count
        total_lines = len(ovl.lines)
        box_width = min(MAX_OVERLAY_BOX_WIDTH, max_x - 4)
        max_box_height = content_height
        # title(1) + lines(total_lines) + hint(1)
        raw_height = min(total_lines + 2, max_box_height)
        box_height = min(raw_height, max_box_height)
        lines_rows = max(1, max_box_height - 2)

        # scroll offset adjustment
        offset = self.state.overlay_offset
        max_offset = max(0, total_lines - lines_rows)

        offset = max(0, min(offset, max_offset))
        self.state.overlay_offset = offset

        top = content_y + max(0, (content_height - box_height) // 2)
        left = max(2, (max_x - box_width) // 2)

        # clear box
        for row in range(box_height):
            self._safe_addnstr(top + row, left, " " * box_width, box_width)

        # title
        title = f"[{ovl.title}]"
        self._safe_addnstr(top, left, title.ljust(box_width), box_width)
        # an empty line
        self._safe_addnstr(top + 1, left, " " * box_width, box_width)

        # content
        row = top + 2
        end_index = min(offset + lines_rows, total_lines)
        for line in ovl.lines[offset:end_index]:
            self._safe_addnstr(row, left, line.ljust(box_width), box_width)
            row += 1

        # hint
        hint = "[ESC key: close]"
        self._safe_addnstr(top + box_height - 1, left, hint.ljust(box_width), box_width)

        # bg color off
        if curses.has_colors() and attr:
            self.stdscr.attroff(attr)

    # internal helpers
    def current_task(self) -> Task | None:
        """Get current task."""
        tasks = self.state.tasks
        if not tasks:
            return None
        # index 0 is dummy for root task addition
        idx = self.state.selected_index
        if idx <= 0:
            return None
        real_idx = idx - 1
        if not (0 <= real_idx < len(tasks)):
            return None
        return tasks[real_idx]

    def _cursor_off(self) -> None:
        """Turn off cursor."""
        if curses.has_colors():
            curses.curs_set(0)
