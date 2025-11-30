# ruff: noqa: C901, T201

import argparse
import sys
from datetime import datetime

from dandori.core.ops import (
    OpsError,
    add_task,
    archive_tree,
    get_task,
    insert_between,
    link_parents,
    list_tasks,
    remove_parent,
    set_requested,
    set_status,
    unarchive_tree,
    update_task,
)
from dandori.core.validate import detect_cycles, detect_inconsistencies
from dandori.interfaces import LENGTH_SHORTEND_ID, tui
from dandori.io.json_io import export_json, import_json
from dandori.io.std_io import print_task
from dandori.storage import Store, StoreToYAML
from dandori.util.dirs import load_env
from dandori.util.ids import parse_id_with_msg
from dandori.util.logger import setup_logger, setup_mode
from dandori.util.time import format_requested_sla

logger = setup_logger("dandori", is_stream=True, is_file=True)


def get_store() -> Store:
    return StoreToYAML()


def _parse_datetime(s: str | None) -> datetime | None:
    """文字列を datetime に変換する。"""
    if s is None:
        return None
    return datetime.fromisoformat(s)


def cmd_add(args: argparse.Namespace) -> int:
    try:
        # 親として追加
        parent_ids = args.depends_on or []
        t = add_task(
            parent_ids=parent_ids,
            title=args.title,
            description=args.description or "",
            priority=args.priority,
            start=_parse_datetime(args.start),
            due=_parse_datetime(args.due),
            tags=args.tags,
            overwrite_id_by=parse_id_with_msg(
                args.id,
                source_ids=[t.id for t in list_tasks()],
            ),
        )

        # 子として追加
        if args.children:
            for cid in args.children:
                link_parents(cid, [t.id])

        print(t.id)
    except OpsError as e:
        _msg = f"An error occurred while adding a task: {e!s}"
        logger.exception(_msg)
        return 1
    else:
        return 0


def cmd_list(args: argparse.Namespace) -> int:
    try:
        tasks = list_tasks(
            status=args.status,  # type: ignore[arg-type]
            archived=args.archived,
            topo=args.topo,
            ready_only=args.ready,
            bottleneck_only=args.bottleneck,
            component_of=parse_id_with_msg(
                args.component,
                source_ids=[t.id for t in list_tasks(archived=None)],
            )
            if args.component
            else None,
        )

        # query フィルタ(ops.list_tasks にはないので後でフィルタ)
        if args.query:
            q = args.query.lower()
            tasks = [t for t in tasks if q in t.title.lower() or q in (t.description or "").lower()]

        for t in tasks:
            _id = t.id[:LENGTH_SHORTEND_ID].ljust(LENGTH_SHORTEND_ID)
            if args.details:
                print_task(t)
                print("-" * 76)
                continue
            marks = []
            if t.is_archived:
                marks.append("A")
            if t.status == "requested":
                marks.append("R")
            if t.status == "in_progress":
                marks.append("I")
            if t.status == "done":
                marks.append("D")
            if t.status == "pending":
                marks.append("P")
            tag = "[" + ",".join(marks) + "]" if marks else " "
            assigned = f" -> {t.assigned_to}" if t.assigned_to else ""
            sla = format_requested_sla(t)
            extra = f" ({sla.unwrap()})" if sla.is_ok() else f" ({sla.unwrap_err()})"
            print(f"{tag} {_id} | p={t.priority} | {t.status}{assigned}{extra} | {t.title}")

    except OpsError as e:
        _msg = f"An error occurred while listing tasks: {e!s}"
        logger.exception(_msg)
        return 1
    else:
        return 0


def cmd_show(args: argparse.Namespace) -> int:
    try:
        if args.id is None:
            logger.exception("id is required")
            return 1
        t = get_task(
            parse_id_with_msg(
                args.id,
                source_ids=[t.id for t in list_tasks()],
            ),
        )
        print_task(t)
    except OpsError as e:
        _msg = f"An error occurred while showing a task: {e!s}"
        logger.exception(_msg)
        return 1
    else:
        return 0


def cmd_update(args: argparse.Namespace) -> int:
    try:
        args_id = parse_id_with_msg(
            args.id,
            source_ids=[t.id for t in list_tasks()],
        )
        # 基本フィールドの更新
        if any(
            [
                args.title is not None,
                args.description is not None,
                args.due is not None,
                args.start is not None,
                args.priority is not None,
                args.tags is not None,
            ],
        ):
            _ = update_task(
                args_id,
                title=args.title,
                description=args.description,
                priority=args.priority,
                start=_parse_datetime(args.start),
                due=_parse_datetime(args.due),
                tags=args.tags,
            )

        # status の更新
        if args.status is not None:
            set_status(args_id, args.status)  # type: ignore[arg-type]

        # request 関連フィールドの更新
        if any(
            [
                args.due is not None,
                args.assign_to is not None,
                args.requested_by is not None,
                args.requested_note is not None,
            ],
        ):
            _ = set_requested(
                args_id,
                due=_parse_datetime(args.due),
                requested_to=args.assign_to,
                requested_by=args.requested_by,
                note=args.requested_note,
            )

        # 親子リンクの追加
        if args.add_parent:
            link_parents(args_id, args.add_parent)
        if args.add_child:
            for cid in args.add_child:
                link_parents(cid, [args_id])

        # 親子リンクの削除
        if args.remove_parent:
            for pid in args.remove_parent:
                remove_parent(args_id, pid)
        if args.remove_child:
            for cid in args.remove_child:
                remove_parent(cid, args_id)

        print(f"updated: {args_id}")
    except OpsError as e:
        _msg = f"An error occurred while updating a task: {e!s}"
        logger.exception(_msg)
        return 1
    else:
        return 0


def cmd_inprogress(args: argparse.Namespace) -> int:
    try:
        args_id = parse_id_with_msg(
            args.id,
            source_ids=[t.id for t in list_tasks()],
        )
        set_status(args_id, "in_progress")
        print(f"in_progress: {args_id}")
    except OpsError as e:
        _msg = f"An error occurred while marking a task as in progress: {e!s}"
        logger.exception(_msg)
        return 1
    else:
        return 0


def cmd_done(args: argparse.Namespace) -> int:
    try:
        args_id = parse_id_with_msg(
            args.id,
            source_ids=[t.id for t in list_tasks()],
        )
        set_status(args_id, "done")
        print(f"done: {args_id}")
    except OpsError as e:
        _msg = f"An error occurred while marking a task as done: {e!s}"
        logger.exception(_msg)
        return 1
    else:
        return 0


def cmd_insert(args: argparse.Namespace) -> int:
    try:
        tasks = list_tasks()
        if args.a is None or args.b is None or args.id is None:
            logger.exception("a, b, and id are required")
            return 1
        a_id = parse_id_with_msg(
            args.a,
            source_ids=[t.id for t in tasks],
        )
        b_id = parse_id_with_msg(
            args.b,
            source_ids=[t.id for t in tasks],
        )
        args_id = parse_id_with_msg(
            args.id,
            source_ids=[t.id for t in tasks],
        )
        new_task = insert_between(
            a_id,
            b_id,
            title=args.title,
            description=args.description or "",
            priority=args.priority,
            tags=args.tags,
            overwrite_id_by=args_id,
        )
        print(new_task.id)
    except OpsError as e:
        _msg = f"An error occurred while inserting a task: {e!s}"
        logger.exception(_msg)
        return 1
    else:
        return 0


def cmd_archive(args: argparse.Namespace) -> int:
    try:
        args_id = parse_id_with_msg(
            args.id,
            source_ids=[t.id for t in list_tasks()],
        )
        ids = archive_tree(args_id)
        print("archived:")
        for i in ids:
            print(" ", i)
    except OpsError as e:
        _msg = f"An error occurred while archiving a task: {e!s}"
        logger.exception(_msg)
        return 1
    else:
        return 0


def cmd_restore(args: argparse.Namespace) -> int:
    try:
        args_id = parse_id_with_msg(
            args.id,
            source_ids=[t.id for t in list_tasks()],
        )
        ids = unarchive_tree(args_id)
        print("restored:")
        for i in ids:
            print(" ", i)
    except OpsError as e:
        _msg = f"An error occurred while restoring a task: {e!s}"
        logger.exception(_msg)
        return 1
    else:
        return 0


def cmd_deps(args: argparse.Namespace) -> int:
    try:
        args_id = parse_id_with_msg(
            args.id,
            source_ids=[t.id for t in list_tasks()],
        )
        t = get_task(args_id)
        print("depends_on:")
        for pid in t.depends_on:
            print(" ", pid)
        print("children:")
        for cid in t.children:
            print(" ", cid)
    except OpsError as e:
        _msg = f"An error occurred while showing depends_on/children IDs: {e!s}"
        logger.exception(_msg)
        return 1
    else:
        return 0


def cmd_reason(args: argparse.Namespace) -> int:
    st = get_store()
    st.load()
    args_id = parse_id_with_msg(
        args.id,
        source_ids=[t.id for t in list_tasks()],
    )
    _info = st.get_dependency_info(args_id)
    if _info.is_err():
        _msg = f"An error occurred while getting dependency info: {_info.unwrap_err()}"
        logger.exception(_msg)
        return 1
    info = _info.unwrap()
    for k, v in info.items():
        print(k + ":")
        for item in v:
            print("  -", item)
    return 0


def cmd_request(args: argparse.Namespace) -> int:
    try:
        env = load_env()
        args_id = parse_id_with_msg(
            args.id,
            source_ids=[t.id for t in list_tasks()],
        )
        set_requested(
            args_id,
            requested_to=args.assignee,
            due=None,  # CLI では due を受け取っていない
            note=args.note or "",
            requested_by=args.requester or env.get("USERNAME", "anonymous"),
        )
        print(f"requested: {args_id} -> {args.assignee}")
    except OpsError as e:
        _msg = f"An error occurred while requesting a task: {e!s}"
        logger.exception(_msg)
        return 1
    else:
        return 0


def cmd_export(args: argparse.Namespace) -> int:
    st = get_store()
    st.load()
    _tasks = st.get_all_tasks()
    if _tasks.is_err():
        _msg = f"An error occurred while exporting tasks: {_tasks.unwrap_err()}"
        logger.exception(_msg)
        return 1
    tasks = _tasks.unwrap()
    export_json(tasks, args.path)
    print(f"exported to {args.path}")
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    st = get_store()
    st.load()
    st.commit()
    _tasks = st.get_all_tasks()
    if _tasks.is_err():
        st.rollback()
        print(f"Error: {_tasks.unwrap_err()}")
        return 1
    tasks = _tasks.unwrap()
    incoming = import_json(args.path)
    for tid, t in incoming.items():
        if tid in tasks:
            # 衝突ポリシー: ID重複は上書きせずスキップ (ログ表示)
            print(f"skip (exists): {tid}")
            continue
        _res = st.add_task(t, id_overwritten=tid)
        if _res.is_err():
            st.rollback()
            print(f"Error: {_res.unwrap_err()}")
            return 1
    st.commit()
    st.save()
    print(f"imported from {args.path}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:  # noqa: ARG001
    st = get_store()
    st.load()
    _tasks = st.get_all_tasks()
    if _tasks.is_err():
        print(f"Error: {_tasks.unwrap_err()}")
        return 1
    tasks = _tasks.unwrap()

    has_errors = False

    # サイクル検出
    cycles = detect_cycles(tasks)
    if cycles:
        has_errors = True
        print("Cycles detected:")
        for cycle in cycles:
            print(f"  {' -> '.join(cycle)}")
    else:
        print("No cycles detected.")

    # 不整合検出
    inconsistencies = detect_inconsistencies(tasks)
    if inconsistencies:
        has_errors = True
        print("\nInconsistencies detected:")
        for tid, issue_type, related_id in inconsistencies:
            if issue_type == "missing_child":
                print(f"  {tid} has depends_on[{related_id}] but {related_id} doesn't have {tid} in children")
            elif issue_type == "missing_parent":
                print(f"  {tid} has children[{related_id}] but {related_id} doesn't have {tid} in depends_on")
    else:
        print("\nNo inconsistencies detected.")

    if has_errors:
        return 1
    print("\nDAG is valid.")
    return 0


def cmd_tui(args: argparse.Namespace) -> int:
    try:
        return tui.run(args)
    except OpsError as e:
        _msg = f"An error occurred while running TUI: {e!s}"
        logger.exception(_msg)
        return 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dandori", description="DAG-based task manager")
    sub = p.add_subparsers(dest="cmd", required=True)

    # log (debug mode)
    p.add_argument("--debug", action="store_true", help="debug mode")
    p.set_defaults(func=lambda args: setup_mode(is_debug=args.debug))

    # add
    sp = sub.add_parser("add", help="add a task")
    sp.add_argument("title")
    sp.add_argument("--description")
    sp.add_argument("--due", help="due date in ISO format")
    sp.add_argument("--start", help="start date in ISO format")
    sp.add_argument("--priority", type=int, default=0)
    sp.add_argument("--id")
    sp.add_argument("--depends-on", nargs="*", help="parent task IDs (',' separated)")
    sp.add_argument("--children", nargs="*", help="child task IDs (',' separated)")
    sp.add_argument("--tags", nargs="*", help="tags (',' separated)")
    sp.add_argument("--metadata", nargs="*", help="metadata in JSON or YAML format")
    sp.set_defaults(func=cmd_add)

    # list
    sp = sub.add_parser("list", help="list tasks")
    sp.add_argument("--status", choices=["pending", "in_progress", "done", "requested", "removed"])
    sp.add_argument("--archived", type=lambda x: x.lower() in ("1", "true", "yes"), default=None)
    sp.add_argument("--query")
    sp.add_argument("--details", action="store_true", help="show detailed information")
    sp.add_argument("--topo", action="store_true", help="topological order")
    sp.add_argument("--topo-mode", choices=["eager", "strict"], default="eager")
    sp.add_argument("--ready", action="store_true", help="show ready tasks only")
    sp.add_argument("--bottleneck", action="store_true", help="show bottleneck tasks only")
    sp.add_argument("--component", help="show tasks in component containing ID")
    sp.set_defaults(func=cmd_list)

    # show
    sp = sub.add_parser("show", help="show task")
    sp.add_argument("id")
    sp.set_defaults(func=cmd_show)

    # update
    sp = sub.add_parser("update", help="update fields of a task")
    sp.add_argument("id")
    sp.add_argument("--title", help="title of the task")
    sp.add_argument("--description")
    sp.add_argument("--due", help="due date in ISO format")
    sp.add_argument("--start", help="start date in ISO format")
    sp.add_argument("--priority", type=int, help="priority of the task")
    sp.add_argument("--tags", nargs="*", help="tags (',' separated)")
    sp.add_argument("--status", choices=["pending", "in_progress", "done", "requested", "removed"])
    sp.add_argument("--assign-to")
    sp.add_argument("--requested-by")
    sp.add_argument("--requested-note")
    sp.add_argument("--add-parent", nargs="*", help="parent task IDs (',' separated)")
    sp.add_argument("--add-child", nargs="*", help="child task IDs (',' separated)")
    sp.add_argument("--remove-parent", nargs="*", help="parent task IDs (',' separated)")
    sp.add_argument("--remove-child", nargs="*", help="child task IDs (',' separated)")
    sp.add_argument("--metadata", nargs="*", help="metadata in JSON or YAML format")
    sp.set_defaults(func=cmd_update)

    # inprogress
    sp = sub.add_parser("inprogress", help="mark in progress")
    sp.add_argument("id")
    sp.set_defaults(func=cmd_inprogress)

    # done
    sp = sub.add_parser("done", help="mark done")
    sp.add_argument("id")
    sp.set_defaults(func=cmd_done)

    # insert
    sp = sub.add_parser("insert", help="insert between A and B")
    sp.add_argument("a")
    sp.add_argument("b")
    sp.add_argument("--title", required=True)
    sp.add_argument("--description")
    sp.add_argument("--priority", type=int, default=0)
    sp.add_argument("--tags", nargs="*")
    sp.add_argument("--id")
    sp.set_defaults(func=cmd_insert)

    # archive / restore
    sp = sub.add_parser("archive", help="archive component containing ID")
    sp.add_argument("id")
    sp.set_defaults(func=cmd_archive)

    sp = sub.add_parser("restore", help="restore component containing ID")
    sp.add_argument("id")
    sp.set_defaults(func=cmd_restore)

    # deps / reason
    sp = sub.add_parser("deps", help="show depends_on/children IDs")
    sp.add_argument("id")
    sp.set_defaults(func=cmd_deps)

    # reason
    sp = sub.add_parser("reason", help="explain relations (why)")
    sp.add_argument("id")
    sp.set_defaults(func=cmd_reason)

    # request (assign + status=requested)
    sp = sub.add_parser("request", help="mark a task as requested to someone")
    sp.add_argument("id")
    sp.add_argument("--to", required=True, dest="assignee")
    sp.add_argument("--by", dest="requester")
    sp.add_argument("--note", dest="note")
    sp.set_defaults(func=cmd_request)

    # export / import
    sp = sub.add_parser("export", help="export to json")
    sp.add_argument("path")
    sp.set_defaults(func=cmd_export)

    sp = sub.add_parser("import", help="import from json")
    sp.add_argument("path")
    sp.set_defaults(func=cmd_import)

    # check
    sp = sub.add_parser("check", help="check DAG for cycles and inconsistencies")
    sp.set_defaults(func=cmd_check)

    # tui
    sp = sub.add_parser("tui", help="run TUI")
    sp.set_defaults(func=cmd_tui)

    return p


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)  # type: ignore[no-any-return]
