from __future__ import annotations

import os
import sys
import threading
import traceback

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

try:
    from core.paths import app_data_dir, resource_root

    APP_DATA_DIR = app_data_dir()
    RESOURCE_ROOT = resource_root()
    os.chdir(APP_DATA_DIR)
    for path in (str(APP_DATA_DIR), str(RESOURCE_ROOT)):
        if path not in sys.path:
            sys.path.insert(0, path)
except Exception:
    APP_DATA_DIR = ROOT
    RESOURCE_ROOT = ROOT

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow

try:
    from core.driver import cleanup_active_drivers, cleanup_orphan_driver_processes
except Exception:
    cleanup_active_drivers = lambda: None
    cleanup_orphan_driver_processes = lambda: 0


def _write_crash_log(text: str) -> None:
    try:
        log_dir = os.path.join(str(APP_DATA_DIR), "logs")
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, "crash.log"), "a", encoding="utf-8") as f:
            f.write(text.rstrip() + "\n\n")
    except Exception:
        pass


def _install_crash_cleanup() -> None:
    old_excepthook = sys.excepthook

    def excepthook(exc_type, exc, tb):
        _write_crash_log("".join(traceback.format_exception(exc_type, exc, tb)))
        cleanup_active_drivers()
        old_excepthook(exc_type, exc, tb)

    sys.excepthook = excepthook

    if hasattr(threading, "excepthook"):
        old_threading_hook = threading.excepthook

        def threading_hook(args):
            _write_crash_log("".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))
            cleanup_active_drivers()
            old_threading_hook(args)

        threading.excepthook = threading_hook


def main():
    cleanup_orphan_driver_processes()
    _install_crash_cleanup()
    app = QApplication.instance() or QApplication(sys.argv)
    app.aboutToQuit.connect(cleanup_active_drivers)
    app.setStyle("Fusion")

    icon_paths = [
        os.path.join(str(APP_DATA_DIR), "OIP-C.ico"),
        os.path.join(str(RESOURCE_ROOT), "OIP-C.ico"),
    ]
    app_icon = None
    for path in icon_paths:
        if os.path.exists(path):
            app_icon = QIcon(path)
            app.setWindowIcon(app_icon)
            break

    win = MainWindow()
    if app_icon is not None and not app_icon.isNull():
        win.setWindowIcon(app_icon)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
