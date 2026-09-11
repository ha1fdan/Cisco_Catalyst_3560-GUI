from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFormLayout, QGroupBox, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget,
)

from core.models import PortInfo, SwitchInfo
from .port_map import PortMapWidget


class DashboardTab(QWidget):
    port_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)

        top_row = QHBoxLayout()

        info_group = QGroupBox("Switch Information")
        info_form = QFormLayout(info_group)
        self.lbl_hostname = QLabel("—")
        self.lbl_model = QLabel("—")
        self.lbl_ios = QLabel("—")
        self.lbl_serial = QLabel("—")
        self.lbl_mac = QLabel("—")
        self.lbl_uptime = QLabel("—")
        self.lbl_http = QLabel("—")
        for lbl in (self.lbl_hostname, self.lbl_model, self.lbl_ios,
                    self.lbl_serial, self.lbl_mac, self.lbl_uptime, self.lbl_http):
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        info_form.addRow("Host Name:", self.lbl_hostname)
        info_form.addRow("Model:", self.lbl_model)
        info_form.addRow("IOS Version:", self.lbl_ios)
        info_form.addRow("Serial Number:", self.lbl_serial)
        info_form.addRow("MAC Address:", self.lbl_mac)
        info_form.addRow("Uptime:", self.lbl_uptime)
        info_form.addRow("HTTP Server:", self.lbl_http)
        top_row.addWidget(info_group, 2)

        health_group = QGroupBox("Switch Health")
        health_form = QFormLayout(health_group)
        self.lbl_fan = QLabel("—")
        self.lbl_temp = QLabel("—")
        self.lbl_ports_up = QLabel("—")
        health_form.addRow("Fan:", self.lbl_fan)
        health_form.addRow("Temperature:", self.lbl_temp)
        health_form.addRow("Ports Up:", self.lbl_ports_up)
        top_row.addWidget(health_group, 1)

        root.addLayout(top_row)

        map_group = QGroupBox("Port Map — hover for details, click to configure")
        map_layout = QVBoxLayout(map_group)
        self.port_map = PortMapWidget()
        self.port_map.port_clicked.connect(self.port_selected.emit)
        map_layout.addWidget(self.port_map)

        legend_row = QHBoxLayout()
        for color, text in (
            ("#22c55e", "Connected"),
            ("#374151", "No Link"),
            ("#6b7280", "Admin Down"),
            ("#ef4444", "Err-Disabled"),
        ):
            swatch = QLabel()
            swatch.setFixedSize(14, 14)
            swatch.setStyleSheet(f"background-color: {color}; border-radius: 3px;")
            legend_row.addWidget(swatch)
            label = QLabel(text)
            label.setStyleSheet("color: gray; font-size: 11px;")
            legend_row.addWidget(label)
            legend_row.addSpacing(10)
        legend_row.addStretch()
        map_layout.addLayout(legend_row)

        root.addWidget(map_group)
        root.addStretch()

        self._sp = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setSizePolicy(self._sp)

    # ------------------------------------------------------------------
    def update_switch_info(self, info: SwitchInfo) -> None:
        self.lbl_hostname.setText(info.hostname or "—")
        self.lbl_model.setText(info.model or "—")
        self.lbl_ios.setText(info.ios_version or "—")
        self.lbl_serial.setText(info.serial_number or "—")
        self.lbl_mac.setText(info.mac_address or "—")
        self.lbl_uptime.setText(info.uptime or "—")
        self.lbl_http.setText("Enabled" if info.http_enabled else "Disabled")

    def update_environment(self, env: dict[str, str]) -> None:
        self.lbl_fan.setText(env.get("fan", "—"))
        self.lbl_temp.setText(env.get("temperature", "—"))

    def update_ports(self, ports: list[PortInfo]) -> None:
        self.port_map.update_ports(ports)
        up_count = sum(1 for p in ports if p.link_status == "connected")
        self.lbl_ports_up.setText(f"{up_count} / {len(ports)}")
