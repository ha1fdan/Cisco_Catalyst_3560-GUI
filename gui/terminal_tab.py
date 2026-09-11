from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QKeyEvent, QTextCursor
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit, QVBoxLayout, QWidget


class HistoryLineEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._history: list[str] = []
        self._index = 0

    def remember(self, command: str) -> None:
        if command and (not self._history or self._history[-1] != command):
            self._history.append(command)
        self._index = len(self._history)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt override
        if event.key() == Qt.Key.Key_Up:
            if self._history and self._index > 0:
                self._index -= 1
                self.setText(self._history[self._index])
            return
        if event.key() == Qt.Key.Key_Down:
            if self._index < len(self._history) - 1:
                self._index += 1
                self.setText(self._history[self._index])
            else:
                self._index = len(self._history)
                self.clear()
            return
        super().keyPressEvent(event)


class TerminalTab(QWidget):
    command_submitted = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        hint = QLabel(
            "Raw CLI passthrough — anything typed here is sent directly to the switch "
            "(exec or config commands). Use this for anything the other tabs don't cover. "
            "Changes made here are not tracked by the GUI until you hit Refresh."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(hint)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setFont(QFont("monospace"))
        layout.addWidget(self.output, 1)

        input_row = QHBoxLayout()
        self.input = HistoryLineEdit()
        self.input.setFont(QFont("monospace"))
        self.input.setPlaceholderText("e.g. show mac address-table, or a config command")
        self.input.returnPressed.connect(self._on_submit)
        send_btn = QPushButton("Send")
        send_btn.clicked.connect(self._on_submit)
        input_row.addWidget(self.input, 1)
        input_row.addWidget(send_btn)
        layout.addLayout(input_row)

    def _on_submit(self) -> None:
        command = self.input.text()
        if not command.strip():
            return
        self.append_line(f"SW# {command}")
        self.input.remember(command)
        self.input.clear()
        self.command_submitted.emit(command)

    def append_line(self, text: str) -> None:
        self.output.moveCursor(QTextCursor.MoveOperation.End)
        self.output.insertPlainText(text if text.endswith("\n") else text + "\n")
        self.output.moveCursor(QTextCursor.MoveOperation.End)

    def append_output(self, text: str) -> None:
        self.append_line(text)
