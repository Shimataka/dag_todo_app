from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pyresults import Err, Ok, Result

from dandori.core.models import Task
from dandori.core.sort import task_sort_key, topo_sort
from dandori.storage import Store, StoreToYAML
from dandori.util.dirs import load_env
from dandori.util.ids import gen_task_id
from dandori.util.time import now_iso

if TYPE_CHECKING:
    from datetime import datetime


Status = Literal["pending", "in_progress", "done", "requested", "removed"]
PREFIX_REQUEST_NOTE = "[request-note]"


class OpsError(Exception):
    """ops 層でのユースケース実行失敗を表す例外。"""


# ---- 内部ユーティリティ ----------------------------------------------------


def _get_store() -> Store:
    """デフォルトの Store 実装を取得する。

    将来 SQLite 対応などで差し替える場合はここを変更する。
    """
    return StoreToYAML()


# ---- 一覧取得 / 個別取得 ----------------------------------------------------


def list_tasks(
    status: Status | None = None,
    *,
    archived: bool | None = False,
    topo: bool = False,
    requested_only: bool = False,
) -> list[Task]:
    """タスク一覧を取得するユースケース。

    status / archived / topo / requested_only を組み合わせてフィルタ・ソートする。
    TUI・REST の両方から利用する想定。
    """
    st = _get_store()
    st.load()
    all_tasks = list[Task](st.get_all_tasks().unwrap_or(default={}).values())

    # archived フラグでフィルタ
    if archived is not None:
        all_tasks = [t for t in all_tasks if t.is_archived == archived]

    # status でフィルタ (requested_only は status と独立)
    if status is not None:
        all_tasks = [t for t in all_tasks if t.status == status]

    # requested_only でフィルタ
    if requested_only:
        all_tasks = [t for t in all_tasks if t.status == "requested"]

    # ソート
    if topo:  # noqa: SIM108
        tasks = topo_sort({t.id: t for t in all_tasks})
    else:
        tasks = sorted(all_tasks, key=lambda t: task_sort_key(t))

    return tasks


def get_task(task_id: str) -> Task:
    """単一タスクを取得するユースケース。見つからない場合は OpsError。"""
    st = _get_store()
    st.load()
    _task = st.get_task(task_id)
    if _task.is_err():
        _msg = f"Task not found: {task_id}"
        raise OpsError(_msg)
    return _task.unwrap()  # type: ignore[no-any-return]


# ---- 追加 / 更新 -----------------------------------------------------------


def add_task(
    parent_ids: list[str],
    title: str,
    *,
    overwrite_id_by: str | None = None,
    description: str = "",
    priority: int | None = None,
    start: datetime | None = None,
    due: datetime | None = None,
    tags: list[str] | None = None,
) -> Task:
    """新規タスクを追加するユースケース。

    parent_ids が空の場合はルートタスクとして追加する。
    parent_ids が指定されていれば、そのタスクの子として追加し、依存エッジを張る。
    """
    env = load_env()
    username = env.get("USERNAME", "anonymous")

    st = _get_store()
    st.load()
    st.commit()

    tid = overwrite_id_by or gen_task_id(username)
    t = Task(
        id=tid,
        title=title,
        description=description or "",
        priority=priority or 0,
        start_date=start.strftime("%Y-%m-%dT%H:%M:%S") if start else None,
        due_date=due.strftime("%Y-%m-%dT%H:%M:%S") if due else None,
        tags=tags or [],
        metadata={},
    )

    # 追加
    res = st.add_task(t)
    if res.is_err():
        st.rollback()
        raise OpsError(res.unwrap_err())

    # 親子リンク
    for parent_id in parent_ids:
        link_res = st.link_tasks(parent_id, t.id)
        if link_res.is_err():
            st.rollback()
            raise OpsError(link_res.unwrap_err())

    t.updated_at = now_iso()
    st.commit()
    st.save()
    return t


def update_task(
    task_id: str,
    *,
    title: str | None = None,
    description: str | None = None,
    priority: int | None = None,
    start: datetime | None = None,
    due: datetime | None = None,
    tags: list[str] | None = None,
    parent_ids: list[str] | None = None,
    children_ids: list[str] | None = None,
) -> Task:
    """タスクの基本フィールドを更新するユースケース。

    status や request 系の変更は set_status / set_requested を利用する。
    """
    st = _get_store()
    st.load()
    st.commit()

    _task = st.get_task(task_id)
    if _task.is_err():
        _msg = f"Task not found: {task_id}"
        raise OpsError(_msg)
    t: Task = _task.unwrap()

    # title (required)
    if title is not None:
        t.title = title
    # description (optional)
    t.description = description or ""
    # priority (optional)
    t.priority = priority
    # start_date (optional)
    t.start_date = start.strftime("%Y-%m-%dT%H:%M:%S") if start else None
    # due_date (optional)
    t.due_date = due.strftime("%Y-%m-%dT%H:%M:%S") if due else None
    # tags (optional)
    t.tags = tags or []
    # parent_ids (optional)
    current_parents = set[str](t.depends_on)
    new_parents = set[str](parent_ids or [])
    to_add = new_parents - current_parents
    match _unsafe_link_parents(
        st,
        child_id=t.id,
        parent_ids=list[str](to_add),
    ):
        case Err(e):
            st.rollback()
            raise e
    to_remove = current_parents - new_parents
    for parent_id in to_remove:
        match _unsafe_unlink_parents(st, child_id=t.id, parent_id=parent_id):
            case Err(e):
                st.rollback()
                raise e
    # children_ids (optional)
    current_children = set[str](t.children)
    new_children = set[str](children_ids or [])
    to_add = new_children - current_children
    match _unsafe_link_children(
        st,
        parent_id=t.id,
        children_ids=list[str](to_add),
    ):
        case Err(e):
            st.rollback()
            raise e
    to_remove = current_children - new_children
    for child_id in to_remove:
        match _unsafe_unlink_children(st, parent_id=t.id, child_id=child_id):
            case Err(e):
                st.rollback()
                raise e

    t.updated_at = now_iso()
    st.commit()
    st.save()
    return t


# ---- 状態変更 --------------------------------------------------------------


def set_status(task_id: str, status: Status) -> Task:
    """Status を直接変更するユースケース（主に done / in_progress 用）。

    archived への変更は archive_tree / unarchive_tree を利用する想定。
    """
    st = _get_store()
    st.load()
    st.commit()

    _task = st.get_task(task_id)
    if _task.is_err():
        _msg = f"Task not found: {task_id}"
        raise OpsError(_msg)
    t: Task = _task.unwrap()
    t.status = status
    t.updated_at = now_iso()

    st.commit()
    st.save()
    return t


def set_requested(
    task_id: str,
    *,
    requested_to: str | None = None,
    due: datetime | None = None,
    note: str | None = None,
    requested_by: str | None = None,
) -> Task:
    """Requested 状態への変更と request 情報の設定をまとめて行うユースケース。

    現状の CLI の cmd_request と同等の振る舞いを想定する：
      - status を "requested" に変更
      - assigned_to を requested_to に設定
      - requested_at の設定がなければ現在時刻に設定
      - requested_by / requested_note を更新
      - due が渡されれば due_date を上書き（SLA 扱い）
    """
    env = load_env()
    requested_by = requested_by or env.get("USERNAME", "anonymous")

    st = _get_store()
    st.load()
    st.commit()

    _task = st.get_task(task_id)
    if _task.is_err():
        _msg = f"Task not found: {task_id}"
        raise OpsError(_msg)
    t: Task = _task.unwrap()

    if requested_to is not None:
        t.assigned_to = requested_to
    if note is not None:
        t.requested_note = f"{PREFIX_REQUEST_NOTE} {note}"
    if due is not None:
        t.due_date = due.strftime("%Y-%m-%dT%H:%M:%S")
    if requested_by is not None:
        t.requested_by = requested_by

    t.status = "requested"
    t.requested_at = now_iso() if t.requested_at is None else t.requested_at
    t.requested_by = requested_by
    t.updated_at = now_iso()

    st.commit()
    st.save()
    return t


def archive_tree(task_id: str) -> list[str]:
    """弱連結成分単位でアーカイブするユースケース。

    戻り値は、アーカイブ状態が変更されたタスクIDのリスト。
    """
    return _toggle_archive_tree(task_id, archive_flag=True)


def unarchive_tree(task_id: str) -> list[str]:
    """弱連結成分単位でアーカイブ解除するユースケース。"""
    return _toggle_archive_tree(task_id, archive_flag=False)


def _toggle_archive_tree(task_id: str, *, archive_flag: bool) -> list[str]:
    st = _get_store()
    st.load()
    st.commit()

    match st.weakly_connected_component(task_id):
        case Ok(comp):
            for t in comp:
                t.is_archived = archive_flag
                t.updated_at = now_iso()
            st.commit()
            st.save()
            return [t.id for t in comp]
        case Err(e):
            st.rollback()
            raise OpsError(e)
        case _:
            st.rollback()
            _msg = "Unexpected error"
            raise OpsError(_msg)


# ---- 依存関係取得 ----------------------------------------------------------


def get_deps(task_id: str) -> list[Task]:
    """指定タスクが依存している親タスク一覧を返すユースケース。"""
    st = _get_store()
    st.load()
    _t = st.get_task(task_id)
    if _t.is_err():
        _msg = f"Task not found: {task_id}"
        raise OpsError(_msg)
    t: Task = _t.unwrap()
    _d = st.get_tasks(t.depends_on)
    if _d.is_err():
        _msg = f"Task not found: {_d.unwrap_err()}"
        raise OpsError(_msg)
    return _d.unwrap()  # type: ignore[no-any-return]


def get_children(task_id: str) -> list[Task]:
    """指定タスクを親とする子タスク一覧を返すユースケース。"""
    st = _get_store()
    st.load()
    _t = st.get_task(task_id)
    if _t.is_err():
        _msg = f"Task not found: {task_id}"
        raise OpsError(_msg)
    t: Task = _t.unwrap()
    _c = st.get_tasks(t.children)
    if _c.is_err():
        _msg = f"Task not found: {_c.unwrap_err()}"
        raise OpsError(_msg)
    return _c.unwrap()  # type: ignore[no-any-return]


# ---- DAG 途中挿入 (将来の REST / TUI 用) ----------------------------------


def insert_between(
    parent_id: str,
    child_id: str,
    *,
    title: str,
    description: str = "",
    priority: int | None = None,
    tags: list[str] | None = None,
    overwrite_id_by: str | None = None,
) -> Task:
    """Parent -> child 間に新しいタスクを挿入するユースケース。

    既存のエッジ parent -> child を
        parent -> new_task -> child
    に張り替えることを想定。
    """
    env = load_env()
    username = env.get("USERNAME", "anonymous")

    st = _get_store()
    st.load()
    st.commit()

    # 新タスク作成
    tid = overwrite_id_by or gen_task_id(username)
    new_task = Task(
        id=tid,
        title=title,
        description=description or "",
        priority=priority or 0,
        tags=tags or [],
    )
    _res = st.insert_task(
        parent_id,
        child_id,
        new_task,
        id_overwritten=overwrite_id_by,
    )
    if _res.is_err():
        st.rollback()
        raise OpsError(_res.unwrap_err())
    new_task.updated_at = now_iso()
    st.commit()
    st.save()
    return new_task


# ---- 親追加ユースケース ---------------------------------


def _unsafe_link_parents(
    store: Store,
    *,
    child_id: str,
    parent_ids: list[str],
) -> Result[None, OpsError]:
    # 存在チェック (少なくとも child / parent の存在は保証しておく) 。
    match store.get_task(child_id):
        case Err(e):
            return Err[None, OpsError](OpsError(e))
    for parent_id in parent_ids:
        match store.get_task(parent_id):
            case Err(e):
                return Err[None, OpsError](OpsError(e))

    for parent_id in parent_ids:
        match store.link_tasks(parent_id, child_id):
            case Err(e):
                store.rollback()
                return Err[None, OpsError](OpsError(e))

    return Ok[None, OpsError](None)


def _unsafe_unlink_parents(
    store: Store,
    *,
    child_id: str,
    parent_id: str,
) -> Result[None, OpsError]:
    match store.unlink_tasks(parent_id, child_id):
        case Err(e):
            store.rollback()
            return Err[None, OpsError](OpsError(e))
    return Ok[None, OpsError](None)


def link_parents(child_id: str, parent_ids: list[str]) -> Task:
    """既存タスク child_id に対して、新たに親 parent_ids をリンクする。

    Store.link_tasks() 側で循環検出が行われる前提。
    循環が検出された場合や link 失敗時は OpsError を送出する。

    戻り値として、親追加後の child Task を返す。
    """
    st = _get_store()
    st.load()
    st.commit()

    match _unsafe_link_parents(st, child_id=child_id, parent_ids=parent_ids):
        case Err(e):
            st.rollback()
            raise e

    st.commit()
    st.save()

    # 最新状態の child を返しておく (children / depends_on の反映確認用)
    _task = st.get_task(child_id)
    if _task.is_err():
        _msg = f"Child task not found: {child_id}"
        raise OpsError(_msg)
    return _task.unwrap()  # type: ignore[no-any-return]


def remove_parent(child_id: str, parent_id: str) -> None:
    """親子関係 parent_id -> child_id を外す。

    循環が検出された場合や unlink 失敗時は OpsError を送出する。
    """
    st = _get_store()
    st.load()
    st.commit()

    match _unsafe_unlink_parents(st, child_id=child_id, parent_id=parent_id):
        case Err(e):
            st.rollback()
            raise e

    st.commit()
    st.save()


# ---- 子追加ユースケース ---------------------------------


def _unsafe_link_children(
    store: Store,
    *,
    parent_id: str,
    children_ids: list[str],
) -> Result[None, OpsError]:
    # 存在チェック (少なくとも parent / child の存在は保証しておく) 。
    match store.get_task(parent_id):
        case Err(e):
            return Err[None, OpsError](OpsError(e))
    for child_id in children_ids:
        match store.get_task(child_id):
            case Err(e):
                return Err[None, OpsError](OpsError(e))

    for child_id in children_ids:
        match store.link_tasks(parent_id, child_id):
            case Err(e):
                store.rollback()
                return Err[None, OpsError](OpsError(e))

    return Ok[None, OpsError](None)


def _unsafe_unlink_children(
    store: Store,
    *,
    parent_id: str,
    child_id: str,
) -> Result[None, OpsError]:
    match store.unlink_tasks(parent_id, child_id):
        case Err(e):
            store.rollback()
            return Err[None, OpsError](OpsError(e))
    return Ok[None, OpsError](None)


def link_children(parent_id: str, children_ids: list[str]) -> Task:
    """既存タスク parent_id に対して、新たに子 child_ids をリンクする。

    Store.link_tasks() 側で循環検出が行われる前提。
    循環が検出された場合や link 失敗時は OpsError を送出する。

    戻り値として、子追加後の parent Task を返す。
    """
    st = _get_store()
    st.load()
    st.commit()

    match _unsafe_link_children(st, parent_id=parent_id, children_ids=children_ids):
        case Err(e):
            st.rollback()
            raise e

    st.commit()
    st.save()

    # 最新状態の parent を返しておく (children / depends_on の反映確認用)
    _task = st.get_task(parent_id)
    if _task.is_err():
        _msg = f"Parent task not found: {parent_id}"
        raise OpsError(_msg)
    return _task.unwrap()  # type: ignore[no-any-return]


def remove_child(parent_id: str, child_id: str) -> None:
    """既存タスク parent_id に対して、子 child_id を削除する。

    unlink 失敗時は OpsError を送出する。
    """
    st = _get_store()
    st.load()
    st.commit()

    match _unsafe_unlink_children(st, parent_id=parent_id, child_id=child_id):
        case Err(e):
            st.rollback()
            raise e

    st.commit()
    st.save()
