from dataclasses import dataclass, field
from typing import Literal

from dandori.core.models import Task

Mode = Literal[
    "list",
    "dialog",
    "overlay",
]
DialogKind = Literal[
    "add",
    "edit",
    "request",
    "filter_tags",
]


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
    ready_only: bool = False  # ready タスクのみ表示フラグ
    bottleneck_only: bool = False  # bottleneck タスクのみ表示フラグ
    component_task_id: str | None = None  # 弱連結成分フィルタのタスクID
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
    profile: str = "default"
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
    dialog_offset: int = 0  # dialog viewのstart rowのオフセット
    overlay_offset: int = 0  # overlay viewのstart rowのオフセット
