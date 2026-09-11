from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QRadioButton, QSpinBox, QStackedWidget, QVBoxLayout,
)

from core.profiles import DeviceProfile, delete_profile, load_profiles, upsert_profile

try:
    from serial.tools import list_ports
except ImportError:  # pragma: no cover
    list_ports = None

BAUD_RATES = [300, 1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200]


@dataclass
class ConnectionParams:
    mode: str                 # "telnet" or "serial"
    host: str = ""
    port: int = 23
    serial_port: str = ""
    baudrate: int = 9600
    password: str = ""
    secret: str = ""


class ConnectionDialog(QDialog):
    """Startup dialog: pick a saved device, or configure a new connection."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Connect to Switch")
        self.setMinimumWidth(440)
        self._result_params: ConnectionParams | None = None
        self._profiles: list[DeviceProfile] = load_profiles()

        layout = QVBoxLayout(self)

        # --- Saved devices ---
        self.saved_group = QGroupBox("Saved Devices")
        saved_layout = QVBoxLayout(self.saved_group)
        self.saved_list = QListWidget()
        self.saved_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.saved_list.itemDoubleClicked.connect(lambda _item: self._connect_selected())
        saved_layout.addWidget(self.saved_list)

        saved_btn_row = QHBoxLayout()
        connect_saved_btn = QPushButton("Connect to Selected")
        connect_saved_btn.clicked.connect(self._connect_selected)
        delete_saved_btn = QPushButton("Delete Selected")
        delete_saved_btn.clicked.connect(self._delete_selected)
        saved_btn_row.addWidget(connect_saved_btn)
        saved_btn_row.addWidget(delete_saved_btn)
        saved_btn_row.addStretch()
        saved_layout.addLayout(saved_btn_row)
        layout.addWidget(self.saved_group)
        self._populate_saved_list()

        # --- New connection ---
        new_group = QGroupBox("New Connection")
        new_layout = QVBoxLayout(new_group)

        mode_row = QHBoxLayout()
        self.radio_telnet = QRadioButton("Telnet")
        self.radio_serial = QRadioButton("Serial (console cable)")
        self.radio_telnet.setChecked(True)
        mode_row.addWidget(self.radio_telnet)
        mode_row.addWidget(self.radio_serial)
        mode_row.addStretch()
        new_layout.addLayout(mode_row)

        self.stack = QStackedWidget()
        new_layout.addWidget(self.stack)

        # --- Telnet page ---
        telnet_page = QGroupBox("Telnet")
        telnet_form = QFormLayout(telnet_page)
        self.host_edit = QLineEdit("192.168.50.1")
        self.tcp_port_spin = QSpinBox()
        self.tcp_port_spin.setRange(1, 65535)
        self.tcp_port_spin.setValue(23)
        telnet_form.addRow("Host / IP:", self.host_edit)
        telnet_form.addRow("TCP Port:", self.tcp_port_spin)
        self.stack.addWidget(telnet_page)

        # --- Serial page ---
        serial_page = QGroupBox("Serial")
        serial_form = QFormLayout(serial_page)
        serial_row = QHBoxLayout()
        self.serial_combo = QComboBox()
        self.serial_combo.setEditable(True)
        self._refresh_serial_ports()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh_serial_ports)
        serial_row.addWidget(self.serial_combo, 1)
        serial_row.addWidget(refresh_btn)
        serial_form.addRow("Device:", serial_row)

        self.baud_combo = QComboBox()
        for rate in BAUD_RATES:
            self.baud_combo.addItem(str(rate), rate)
        self.baud_combo.setCurrentText("9600")
        serial_form.addRow("Baud rate:", self.baud_combo)
        self.stack.addWidget(serial_page)

        self.radio_telnet.toggled.connect(
            lambda checked: self.stack.setCurrentIndex(0 if checked else 1)
        )

        # --- Credentials ---
        cred_group = QGroupBox("Credentials")
        cred_form = QFormLayout(cred_group)
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.secret_edit = QLineEdit()
        self.secret_edit.setEchoMode(QLineEdit.EchoMode.Password)
        cred_form.addRow("Line password:", self.password_edit)
        cred_form.addRow("Enable secret:", self.secret_edit)
        new_layout.addWidget(cred_group)

        hint = QLabel(
            "Line password logs into user EXEC mode (con/vty).\n"
            "Enable secret is used to reach privileged EXEC mode."
        )
        hint.setStyleSheet("color: gray; font-size: 11px;")
        new_layout.addWidget(hint)

        # --- Save-as-profile ---
        save_row = QHBoxLayout()
        self.save_check = QCheckBox("Save this device for next time")
        self.save_check.toggled.connect(self._on_save_toggled)
        self.save_name_edit = QLineEdit()
        self.save_name_edit.setPlaceholderText("Device name (e.g. SW02 - Lab)")
        self.save_name_edit.setEnabled(False)
        save_row.addWidget(self.save_check)
        save_row.addWidget(self.save_name_edit, 1)
        new_layout.addLayout(save_row)

        layout.addWidget(new_group)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Connect")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------
    def _populate_saved_list(self) -> None:
        self.saved_list.clear()
        for profile in self._profiles:
            item = QListWidgetItem(profile.summary())
            item.setData(Qt.ItemDataRole.UserRole, profile.name)
            self.saved_list.addItem(item)
        self.saved_group.setVisible(bool(self._profiles))

    def _selected_profile(self) -> DeviceProfile | None:
        items = self.saved_list.selectedItems()
        if not items:
            return None
        name = items[0].data(Qt.ItemDataRole.UserRole)
        return next((p for p in self._profiles if p.name == name), None)

    def _connect_selected(self) -> None:
        profile = self._selected_profile()
        if profile is None:
            QMessageBox.information(self, "No selection", "Select a saved device first.")
            return
        self._result_params = ConnectionParams(
            mode=profile.mode,
            host=profile.host,
            port=profile.port,
            serial_port=profile.serial_port,
            baudrate=profile.baudrate,
            password=profile.password,
            secret=profile.secret,
        )
        self.accept()

    def _delete_selected(self) -> None:
        profile = self._selected_profile()
        if profile is None:
            QMessageBox.information(self, "No selection", "Select a saved device first.")
            return
        confirm = QMessageBox.question(self, "Delete device", f"Delete saved device '{profile.name}'?")
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self._profiles = delete_profile(profile.name)
        self._populate_saved_list()

    def _on_save_toggled(self, checked: bool) -> None:
        self.save_name_edit.setEnabled(checked)
        if checked and not self.save_name_edit.text().strip():
            default = self.host_edit.text().strip() if self.radio_telnet.isChecked() \
                else self.serial_combo.currentText().strip()
            self.save_name_edit.setText(default)

    def _refresh_serial_ports(self) -> None:
        current = self.serial_combo.currentText()
        self.serial_combo.clear()
        ports = []
        if list_ports is not None:
            ports = [p.device for p in list_ports.comports()]
        if not ports:
            ports = ["/dev/ttyUSB0"]
        self.serial_combo.addItems(ports)
        if current:
            self.serial_combo.setEditText(current)

    def _on_accept(self) -> None:
        if self.radio_telnet.isChecked():
            self._result_params = ConnectionParams(
                mode="telnet",
                host=self.host_edit.text().strip(),
                port=self.tcp_port_spin.value(),
                password=self.password_edit.text(),
                secret=self.secret_edit.text(),
            )
        else:
            self._result_params = ConnectionParams(
                mode="serial",
                serial_port=self.serial_combo.currentText().strip(),
                baudrate=int(self.baud_combo.currentData()),
                password=self.password_edit.text(),
                secret=self.secret_edit.text(),
            )

        if self.save_check.isChecked():
            name = self.save_name_edit.text().strip()
            if not name:
                QMessageBox.warning(self, "Missing name", "Enter a name to save this device as.")
                return
            upsert_profile(DeviceProfile(
                name=name,
                mode=self._result_params.mode,
                host=self._result_params.host,
                port=self._result_params.port,
                serial_port=self._result_params.serial_port,
                baudrate=self._result_params.baudrate,
                password=self._result_params.password,
                secret=self._result_params.secret,
            ))

        self.accept()

    def result_params(self) -> ConnectionParams | None:
        return self._result_params
