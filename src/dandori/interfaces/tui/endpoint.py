import argparse
import curses

from dandori.interfaces.tui.app import App


def main(stdscr: curses.window, args: argparse.Namespace | None = None) -> int:
    app = App(stdscr, args)
    while True:
        app.view.draw()
        key_raw = stdscr.get_wch()
        key = ord(key_raw) if isinstance(key_raw, str) else key_raw
        ch = key_raw if isinstance(key_raw, str) else None
        cont = app.handle_key(key, ch)
        if not cont:
            break
    return 0


def run(args: argparse.Namespace | None = None) -> int:
    return curses.wrapper(main, args)
