# ruff: noqa: C901, T201

import argparse
import sys

from dandori.core.models import Task
from dandori.core.sort import task_sort_key, topo_sort
from dandori.core.validate import detect_cycles, detect_inconsistencies
from dandori.io.json_io import export_json, import_json
from dandori.io.std_io import print_task
from dandori.storage import Store, StoreToYAML
from dandori.util.dirs import load_env
from dandori.util.ids import gen_task_id
from dandori.util.time import format_requested_sla, now_iso


def get_store() -> Store:
    return StoreToYAML()


def cmd_add(args: argparse.Namespace) -> int:
    env = load_env()
    st = get_store()
    st.load()

    tid = gen_task_id(env["USERNAME"]) if args.id is None else args.id
    t = Task(
        id=tid,
        title=args.title,
        description=args.description or "",
        due_date=args.due,
        start_date=args.start,
        priority=args.priority,
    )
    st.add_task(t)

    # 親子リンク
    for pid in args.depends_on or []:
        st.link(pid, t.id)
    for cid in args.children or []:
        st.link(t.id, cid)

    st.save()
    print(t.id)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    st = get_store()
    st.load()
    _tasks = st.get_all_tasks()
    if _tasks.is_err():
        print(f"Error: {_tasks.unwrap_err()}")
        return 1
    tasks = list[Task](_tasks.unwrap().values())

    # フィルタ
    if args.status:
        tasks = [t for t in tasks if t.status == args.status]
    if args.archived is not None:
        tasks = [t for t in tasks if t.is_archived == args.archived]
    if args.query:
        q = args.query.lower()
        tasks = [t for t in tasks if q in t.title.lower() or q in (t.description or "").lower()]

    # ソート
    if args.topo:
        tasks = topo_sort({t.id: t for t in tasks})
    else:
        tasks.sort(key=task_sort_key)

    for t in tasks:
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
        extra = f" ({sla})" if sla else ""
        print(f"{tag} {t.id} | p={t.priority} | {t.status}{assigned}{extra} | {t.title}")

    return 0


def cmd_show(args: argparse.Namespace) -> int:
    st = get_store()
    st.load()
    t = st.get(args.id)
    if t.is_err():
        print(f"Error: {t.unwrap_err()}")
        return 1
    print_task(t.unwrap())
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    st = get_store()
    st.load()
    _t = st.get(args.id)
    if _t.is_err():
        print(f"Error: {_t.unwrap_err()}")
        return 1
    t = _t.unwrap()

    if args.title is not None:
        t.title = args.title
    if args.description is not None:
        t.description = args.description
    if args.due is not None:
        t.due_date = args.due
    if args.start is not None:
        t.start_date = args.start
    if args.priority is not None:
        t.priority = args.priority
    if args.status is not None:
        t.status = args.status
    if args.assign_to is not None:
        t.assigned_to = args.assign_to
    if args.requested_by is not None:
        t.requested_by = args.requested_by
    if args.requested_at is not None:
        t.requested_at = args.requested_at
    if args.requested_note is not None:
        t.requested_note = args.requested_note

    for pid in args.add_parent or []:
        st.link(pid, t.id)
    for cid in args.add_child or []:
        st.link(t.id, cid)
    for pid in args.remove_parent or []:
        st.unlink(pid, t.id)
    for cid in args.remove_child or []:
        st.unlink(t.id, cid)

    t.updated_at = now_iso()
    st.save()
    print(f"updated: {t.id}")
    return 0


def cmd_done(args: argparse.Namespace) -> int:
    # done は update --status done のラッパー
    update_args = argparse.Namespace(
        id=args.id,
        title=None,
        description=None,
        due=None,
        start=None,
        priority=None,
        status="done",
        assign_to=None,
        requested_by=None,
        requested_at=None,
        requested_note=None,
        add_parent=None,
        add_child=None,
        remove_parent=None,
        remove_child=None,
    )
    result = cmd_update(update_args)
    if result == 0:
        print(f"done: {args.id}")
    return result


def cmd_insert(args: argparse.Namespace) -> int:
    st = get_store()
    st.load()
    env = load_env()

    new_id = gen_task_id(env["USERNAME"]) if args.id is None else args.id
    new_task = Task(id=new_id, title=args.title, description=args.description or "")
    st.insert_between(args.a, args.b, new_task)
    st.save()
    print(new_task.id)
    return 0


def cmd_archive(args: argparse.Namespace) -> int:
    st = get_store()
    st.load()
    _ids = st.archive_component(args.id, flag=True)
    if _ids.is_err():
        print(f"Error: {_ids.unwrap_err()}")
        return 1
    ids = _ids.unwrap()
    st.save()
    print("archived:")
    for i in ids:
        print(" ", i)
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    st = get_store()
    st.load()
    _ids = st.archive_component(args.id, flag=False)
    if _ids.is_err():
        print(f"Error: {_ids.unwrap_err()}")
        return 1
    ids = _ids.unwrap()
    st.save()
    print("restored:")
    for i in ids:
        print(" ", i)
    return 0


def cmd_deps(args: argparse.Namespace) -> int:
    st = get_store()
    st.load()
    _t = st.get(args.id)
    if _t.is_err():
        print(f"Error: {_t.unwrap_err()}")
        return 1
    t = _t.unwrap()
    print("depends_on:")
    for pid in t.depends_on:
        print(" ", pid)
    print("children:")
    for cid in t.children:
        print(" ", cid)
    return 0


def cmd_reason(args: argparse.Namespace) -> int:
    st = get_store()
    st.load()
    _info = st.reason(args.id)
    if _info.is_err():
        print(f"Error: {_info.unwrap_err()}")
        return 1
    info = _info.unwrap()
    for k, v in info.items():
        print(k + ":")
        for item in v:
            print("  -", item)
    return 0


def cmd_request(args: argparse.Namespace) -> int:
    # request は update --status requested --assign-to ... のラッパー
    env = load_env()
    requested_note = f"[request-note] {args.note}" if args.note else None
    update_args = argparse.Namespace(
        id=args.id,
        title=None,
        description=None,
        due=None,
        start=None,
        priority=None,
        status="requested",
        assign_to=args.assignee,
        requested_by=args.requester or env.get("USERNAME", "anonymous"),
        requested_at=now_iso(),
        requested_note=requested_note,
        add_parent=None,
        add_child=None,
        remove_parent=None,
        remove_child=None,
    )
    result = cmd_update(update_args)
    if result == 0:
        print(f"requested: {args.id} -> {args.assignee}")
    return result


def cmd_export(args: argparse.Namespace) -> int:
    st = get_store()
    st.load()
    _tasks = st.get_all_tasks()
    if _tasks.is_err():
        print(f"Error: {_tasks.unwrap_err()}")
        return 1
    tasks = _tasks.unwrap()
    export_json(tasks, args.path)
    print(f"exported to {args.path}")
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    st = get_store()
    st.load()
    _tasks = st.get_all_tasks()
    if _tasks.is_err():
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
            print(f"Error: {_res.unwrap_err()}")
            return 1
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


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dandori", description="DAG-based task manager")
    sub = p.add_subparsers(dest="cmd", required=True)

    # add
    sp = sub.add_parser("add", help="add a task")
    sp.add_argument("title")
    sp.add_argument("--description")
    sp.add_argument("--due")
    sp.add_argument("--start")
    sp.add_argument("--priority", type=int, default=0)
    sp.add_argument("--id")
    sp.add_argument("--depends-on", nargs="*")
    sp.add_argument("--children", nargs="*")
    sp.set_defaults(func=cmd_add)

    # list
    sp = sub.add_parser("list", help="list tasks")
    sp.add_argument("--status")
    sp.add_argument("--archived", type=lambda x: x.lower() in ("1", "true", "yes"), default=None)
    sp.add_argument("--query")
    sp.add_argument("--details", action="store_true", help="show detailed information")
    sp.add_argument("--topo", action="store_true", help="topological order")
    sp.add_argument("--topo-mode", choices=["eager", "strict"], default="eager")
    sp.set_defaults(func=cmd_list)

    # show
    sp = sub.add_parser("show", help="show task")
    sp.add_argument("id")
    sp.set_defaults(func=cmd_show)

    # update
    sp = sub.add_parser("update", help="update fields of a task")
    sp.add_argument("id")
    sp.add_argument("--title")
    sp.add_argument("--description")
    sp.add_argument("--due")
    sp.add_argument("--start")
    sp.add_argument("--priority", type=int)
    sp.add_argument("--status")
    sp.add_argument("--assign-to")
    sp.add_argument("--requested-by")
    sp.add_argument("--requested-at")
    sp.add_argument("--requested-note")
    sp.add_argument("--add-parent", nargs="*")
    sp.add_argument("--add-child", nargs="*")
    sp.add_argument("--remove-parent", nargs="*")
    sp.add_argument("--remove-child", nargs="*")
    sp.set_defaults(func=cmd_update)

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

    return p


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)  # type: ignore[no-any-return]
