#!/usr/bin/env python3
"""Entry point for the Cisco Catalyst 3560 GUI manager."""
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from gui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Cisco Catalyst 3560 GUI")

    window = MainWindow()
    window.show()
    QTimer.singleShot(0, window.show_connect_dialog)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
