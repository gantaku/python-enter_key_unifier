"""Tray-resident app: Enter = newline, Ctrl+Enter = send, in the apps listed in config.json."""

from __future__ import annotations

import logging
import os
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

from src import __version__
from src.config import ConfigError, app_dir, load_rules
from src.engine import Engine
from src.rules import Rule

log = logging.getLogger("enter_key_unifier")

MUTEX_NAME = "Local\\enter_key_unifier"
ERROR_ALREADY_EXISTS = 183


class RuleStore:
    """Rules reloaded when config.json changes. An invalid file keeps the last good rules.

    The hook thread only reads the current tuple; reloading (file I/O) runs on a
    background timer so the low-level hook always answers quickly.
    """

    RELOAD_INTERVAL = 2.0

    def __init__(self, path: Path):
        self._path = path
        self._mtime: int | None = None
        self._checked = False
        self._rules: tuple[Rule, ...] = ()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.reload_if_changed()

    def __call__(self) -> tuple[Rule, ...]:
        return self._rules

    def start_watching(self) -> None:
        def loop():
            while not self._stop.wait(self.RELOAD_INTERVAL):
                self.reload_if_changed()

        threading.Thread(target=loop, name="config-watch", daemon=True).start()

    def stop_watching(self) -> None:
        self._stop.set()

    def reload_if_changed(self) -> None:
        try:
            mtime = self._path.stat().st_mtime_ns
        except OSError:
            mtime = None
        if self._checked and mtime == self._mtime:
            return
        self._checked = True
        with self._lock:
            try:
                self._rules = load_rules(self._path)
                log.info("config loaded: %s", [r.name for r in self._rules])
            except ConfigError as error:
                kept = (
                    "keeping the previous rules" if self._rules else "no rules active"
                )
                log.error("invalid settings (%s); %s", error, kept)
            try:
                self._mtime = self._path.stat().st_mtime_ns
            except OSError:
                self._mtime = None


def setup_logging(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    log_path = directory / "app.log"
    handler = RotatingFileHandler(
        log_path, maxBytes=1_000_000, backupCount=2, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    return log_path


def acquire_single_instance():
    import win32api
    import win32event

    mutex = win32event.CreateMutex(None, False, MUTEX_NAME)
    if win32api.GetLastError() == ERROR_ALREADY_EXISTS:
        return None
    return mutex


def make_icon_image(paused: bool):
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    color = (128, 128, 128, 255) if paused else (22, 163, 74, 255)
    draw.rounded_rectangle((4, 4, 60, 60), radius=12, fill=color)
    # Return-key arrow
    draw.line((46, 16, 46, 38, 18, 38), fill="white", width=6)
    draw.polygon(((12, 38), (24, 28), (24, 48)), fill="white")
    return image


def run_tray(
    paused: threading.Event, config_path: Path, log_path: Path, on_quit
) -> None:
    import pystray

    title = f"Enter Key Unifier {__version__}"

    def toggle_pause(icon, _item):
        if paused.is_set():
            paused.clear()
        else:
            paused.set()
        icon.icon = make_icon_image(paused.is_set())
        icon.title = f"{title}（一時停止中）" if paused.is_set() else title
        log.info("paused" if paused.is_set() else "resumed")

    def open_file(path: Path):
        return lambda _icon, _item: os.startfile(str(path))

    def quit_app(icon, _item):
        on_quit()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem(
            "一時停止", toggle_pause, checked=lambda _item: paused.is_set()
        ),
        pystray.MenuItem("設定ファイルを開く", open_file(config_path)),
        pystray.MenuItem("ログを開く", open_file(log_path)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("終了", quit_app),
    )
    pystray.Icon("enter_key_unifier", make_icon_image(False), title, menu).run()


def main() -> int:
    if sys.platform != "win32":
        print("Only Windows is supported in this version.", file=sys.stderr)
        return 1
    from src.platform_win import KeyboardHook, WindowsProbe

    directory = app_dir()
    log_path = setup_logging(directory)
    mutex = acquire_single_instance()
    if mutex is None:
        log.info("already running; exit")
        return 0
    log.info("start %s", __version__)
    config_path = directory / "config.json"
    paused = threading.Event()
    rules = RuleStore(config_path)
    rules.start_watching()
    engine = Engine(WindowsProbe(rules), paused=paused.is_set)
    hook = KeyboardHook(engine)
    hook.start()
    try:
        run_tray(paused, config_path, log_path, on_quit=hook.stop)
    finally:
        hook.stop()
        rules.stop_watching()
        log.info("stop")
    return 0


if __name__ == "__main__":
    sys.exit(main())
