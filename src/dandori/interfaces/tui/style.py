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

LENGTH_SHORTEND_ID = 8


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
        status_line = "List: [↑/↓ Move, [/] Scroll] [(q)uit] "
        status_line += f"[(f/F)ilter: {status_label}] [(a)rchived: {archived_label}] "
        status_line += f"[(t)opo: {topo_label}] [(r)equested: {req_label}]"
        return status_line

    @classmethod
    def _help_line(cls) -> str:
        help_line = "Task: [(A)dd] [(E)dit] [(R)equest] [(G)raph] "
        help_line += "[(P)end] [(I)n_progress] [(D)one] [(X)Archive] [(U)narchive]"
        return help_line
