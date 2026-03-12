import argparse
import curses

from dandori.interfaces.tui.app import App


def main(stdscr: curses.window, args: argparse.Namespace | None = None) -> int:
    app = App(stdscr, args)
    while True:
        app.view.draw()

        if args is not None and args.watch is not None and args.watch > 0:
            stdscr.timeout(100)

        try:
            key_raw = stdscr.get_wch()
        except curses.error:
            app.maybe_auto_reload()
            continue

        key = ord(key_raw) if isinstance(key_raw, str) else key_raw
        ch = key_raw if isinstance(key_raw, str) else None
        cont = app.handle_key(key, ch)
        if not cont:
            break
    return 0


def run(args: argparse.Namespace | None = None) -> int:
    return curses.wrapper(main, args)
