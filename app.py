from __future__ import annotations

import os
import sys

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


def main():
    app = QApplication.instance() or QApplication(sys.argv)
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
