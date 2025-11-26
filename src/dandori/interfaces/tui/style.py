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
        _title = "--- dandori (TUI) > Topological graph TODO task manager ---"
        _title += " [↑/↓ Move, [/] Scroll] [(q)uit]"
        return _title

    @classmethod
    def status(
        cls,
        status_label: str,
        archived_label: str,
        topo_label: str,
        req_label: str,
        ready_label: str,
        bottleneck_label: str,
        component_label: str,
    ) -> str:
        return cls._status_line(
            status_label,
            archived_label,
            topo_label,
            req_label,
            ready_label,
            bottleneck_label,
            component_label,
        )

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
        ready_label: str,
        bottleneck_label: str,
        component_label: str,
    ) -> str:
        return "".join(
            [
                "List: ",
                f"[(f/F)ilter: {status_label}] ",
                f"[(a)rchived: {archived_label}] ",
                f"[(t)opo: {topo_label}] ",
                f"[(r)equested: {req_label}] ",
                f"[(y)ready: {ready_label}] ",
                f"[(b)ottleneck: {bottleneck_label}] ",
                f"[(c)omponent: {component_label}]",
            ],
        )

    @classmethod
    def _help_line(cls) -> str:
        help_line = "Task: "
        help_line += "[(A)dd] "
        help_line += "[(E)dit] "
        help_line += "[(R)equest] "
        help_line += "[(G)raph] "
        help_line += "[(P)end] "
        help_line += "[(I)n_progress] "
        help_line += "[(D)one] "
        help_line += "[(X)archive] "
        help_line += "[(U)narchive]"
        return help_line
