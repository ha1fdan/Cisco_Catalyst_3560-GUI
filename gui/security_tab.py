from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from core.models import LineConfig, UserAccount

LINE_LABELS = {
    "con 0": "Console (con 0)",
    "vty 0 4": "Telnet/SSH sessions 1-5 (vty 0 4)",
    "vty 5 15": "Telnet/SSH sessions 6-16 (vty 5 15)",
}


class AddUserDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Local User")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.username_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.privilege_spin = QSpinBox()
        self.privilege_spin.setRange(0, 15)
        self.privilege_spin.setValue(15)
        form.addRow("Username:", self.username_edit)
        form.addRow("Password:", self.password_edit)
        form.addRow("Privilege:", self.privilege_spin)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> tuple[str, str, int]:
        return (
            self.username_edit.text().strip(),
            self.password_edit.text(),
            self.privilege_spin.value(),
        )


class SecurityTab(QWidget):
    set_hostname_requested = Signal(str)
    set_enable_secret_requested = Signal(str)
    set_line_password_requested = Signal(str, str)
    set_http_server_requested = Signal(bool)
    add_user_requested = Signal(str, str, int)
    delete_user_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._users: list[UserAccount] = []
        self._columns_sized = False
        layout = QVBoxLayout(self)

        identity_group = QGroupBox("Identity")
        identity_form = QFormLayout(identity_group)
        host_row = QHBoxLayout()
        self.hostname_edit = QLineEdit()
        host_apply = QPushButton("Apply")
        host_apply.clicked.connect(
            lambda: self.set_hostname_requested.emit(self.hostname_edit.text().strip())
        )
        host_row.addWidget(self.hostname_edit)
        host_row.addWidget(host_apply)
        identity_form.addRow("Hostname:", host_row)
        layout.addWidget(identity_group)

        auth_group = QGroupBox("Privileged Mode")
        auth_form = QFormLayout(auth_group)
        secret_row = QHBoxLayout()
        self.secret_edit = QLineEdit()
        self.secret_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.secret_edit.setPlaceholderText("new enable secret")
        secret_apply = QPushButton("Apply")
        secret_apply.clicked.connect(self._on_apply_secret)
        secret_row.addWidget(self.secret_edit)
        secret_row.addWidget(secret_apply)
        auth_form.addRow("Enable Secret:", secret_row)
        layout.addWidget(auth_group)

        lines_group = QGroupBox("Line Passwords")
        lines_form = QFormLayout(lines_group)
        self.line_edits: dict[str, QLineEdit] = {}
        self.line_status_labels: dict[str, QLabel] = {}
        for line_id, label in LINE_LABELS.items():
            row = QHBoxLayout()
            edit = QLineEdit()
            edit.setEchoMode(QLineEdit.EchoMode.Password)
            edit.setPlaceholderText("new password")
            status = QLabel("—")
            status.setStyleSheet("color: gray; font-size: 11px;")
            apply_btn = QPushButton("Apply")
            apply_btn.clicked.connect(
                lambda checked=False, lid=line_id: self._on_apply_line(lid)
            )
            row.addWidget(edit, 2)
            row.addWidget(status, 1)
            row.addWidget(apply_btn)
            lines_form.addRow(label + ":", row)
            self.line_edits[line_id] = edit
            self.line_status_labels[line_id] = status
        layout.addWidget(lines_group)

        http_group = QGroupBox("Web Management")
        http_form = QFormLayout(http_group)
        self.http_check = QCheckBox("HTTP server enabled (port 80, no HTTPS on this image)")
        self.http_check.toggled.connect(self.set_http_server_requested.emit)
        http_form.addRow(self.http_check)
        layout.addWidget(http_group)

        users_group = QGroupBox("Local Users")
        users_layout = QVBoxLayout(users_group)
        users_btn_row = QHBoxLayout()
        self.add_user_btn = QPushButton("Add User")
        self.delete_user_btn = QPushButton("Delete Selected")
        self.add_user_btn.clicked.connect(self._on_add_user)
        self.delete_user_btn.clicked.connect(self._on_delete_user)
        users_btn_row.addWidget(self.add_user_btn)
        users_btn_row.addWidget(self.delete_user_btn)
        users_btn_row.addStretch()
        users_layout.addLayout(users_btn_row)

        self.users_table = QTableWidget(0, 2)
        self.users_table.setHorizontalHeaderLabels(["Username", "Privilege"])
        self.users_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.users_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.users_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        users_layout.addWidget(self.users_table)
        layout.addWidget(users_group)

    # ------------------------------------------------------------------
    def update_hostname(self, hostname: str) -> None:
        if not self.hostname_edit.hasFocus():
            self.hostname_edit.setText(hostname)

    def update_lines(self, lines: list[LineConfig]) -> None:
        for lc in lines:
            label = self.line_status_labels.get(lc.line)
            if label is None:
                continue
            state = "password set" if lc.has_password else "no password"
            label.setText(f"{lc.login_method}, {state}")

    def update_http(self, enabled: bool) -> None:
        self.http_check.blockSignals(True)
        self.http_check.setChecked(enabled)
        self.http_check.blockSignals(False)

    def update_users(self, users: list[UserAccount]) -> None:
        self._users = users
        self.users_table.setRowCount(len(users))
        for row, u in enumerate(users):
            self.users_table.setItem(row, 0, QTableWidgetItem(u.username))
            self.users_table.setItem(row, 1, QTableWidgetItem(str(u.privilege)))
        if not self._columns_sized and users:
            self.users_table.resizeColumnsToContents()
            self._columns_sized = True

    # ------------------------------------------------------------------
    def _on_apply_secret(self) -> None:
        secret = self.secret_edit.text()
        if not secret:
            QMessageBox.warning(self, "Empty secret", "Enter a new enable secret first.")
            return
        self.set_enable_secret_requested.emit(secret)
        self.secret_edit.clear()

    def _on_apply_line(self, line_id: str) -> None:
        edit = self.line_edits[line_id]
        password = edit.text()
        if not password:
            QMessageBox.warning(self, "Empty password", "Enter a new password first.")
            return
        self.set_line_password_requested.emit(line_id, password)
        edit.clear()

    def _on_add_user(self) -> None:
        dlg = AddUserDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            username, password, privilege = dlg.values()
            if not username or not password:
                QMessageBox.warning(self, "Missing data", "Username and password are required.")
                return
            self.add_user_requested.emit(username, password, privilege)

    def _on_delete_user(self) -> None:
        rows = self.users_table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "No selection", "Select a user first.")
            return
        user = self._users[rows[0].row()]
        confirm = QMessageBox.question(self, "Delete user", f"Delete user '{user.username}'?")
        if confirm == QMessageBox.StandardButton.Yes:
            self.delete_user_requested.emit(user.username)
