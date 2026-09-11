from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QRadioButton, QSpinBox, QStackedWidget,
    QVBoxLayout,
)

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
    """Startup dialog asking how to reach the switch."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Connect to Switch")
        self.setMinimumWidth(420)
        self._result_params: ConnectionParams | None = None

        layout = QVBoxLayout(self)

        mode_row = QHBoxLayout()
        self.radio_telnet = QRadioButton("Telnet")
        self.radio_serial = QRadioButton("Serial (console cable)")
        self.radio_telnet.setChecked(True)
        mode_row.addWidget(self.radio_telnet)
        mode_row.addWidget(self.radio_serial)
        mode_row.addStretch()
        layout.addLayout(mode_row)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack)

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
        layout.addWidget(cred_group)

        hint = QLabel(
            "Line password logs into user EXEC mode (con/vty).\n"
            "Enable secret is used to reach privileged EXEC mode."
        )
        hint.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Connect")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

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
        self.accept()

    def result_params(self) -> ConnectionParams | None:
        return self._result_params
