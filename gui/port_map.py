from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget

from core.models import PortInfo

_STATUS_COLORS = {
    "admin_down": "#6b7280",   # gray - shut down
    "connected": "#22c55e",    # green - link up
    "notconnect": "#374151",   # dark slate - enabled, no link
    "disabled": "#6b7280",
    "err-disabled": "#ef4444", # red
    "monitoring": "#eab308",
    "unknown": "#4b5563",
}


class PortCell(QFrame):
    clicked = Signal(str)

    def __init__(self, port_name: str, label: str, parent=None):
        super().__init__(parent)
        self.port_name = port_name
        self.setFixedSize(36, 32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._label = QLabel(label)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet("font-size: 10px; font-weight: 600; color: white; background: transparent;")
        layout.addWidget(self._label)
        self.set_status("unknown", True, f"{port_name} (no data yet)")

    def set_status(self, link_status: str, admin_up: bool, tooltip: str) -> None:
        if not admin_up:
            color = _STATUS_COLORS["admin_down"]
        else:
            color = _STATUS_COLORS.get(link_status, _STATUS_COLORS["unknown"])
        self.setStyleSheet(
            f"QFrame {{ background-color: {color}; border: 1px solid #111827; border-radius: 4px; }}"
        )
        self.setToolTip(tooltip)

    def mousePressEvent(self, event):  # noqa: N802 - Qt override
        self.clicked.emit(self.port_name)
        super().mousePressEvent(event)


class PortMapWidget(QWidget):
    """Visual front-panel layout mirroring the real WS-C3560-24TS."""

    port_clicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        grid = QGridLayout(self)
        grid.setSpacing(4)
        self.cells: dict[str, PortCell] = {}

        for i in range(12):
            odd, even = 2 * i + 1, 2 * i + 2
            for row, num in ((0, odd), (1, even)):
                name = f"Fa0/{num}"
                cell = PortCell(name, str(num))
                cell.clicked.connect(self.port_clicked.emit)
                grid.addWidget(cell, row, i)
                self.cells[name] = cell

        grid.setColumnMinimumWidth(12, 18)

        for row, num in ((0, 1), (1, 2)):
            name = f"Gi0/{num}"
            cell = PortCell(name, f"G{num}")
            cell.clicked.connect(self.port_clicked.emit)
            grid.addWidget(cell, row, 13)
            self.cells[name] = cell

    def update_ports(self, ports: list[PortInfo]) -> None:
        for p in ports:
            cell = self.cells.get(p.name)
            if cell is None:
                continue
            vlan_desc = p.access_vlan if p.mode == "access" else (p.trunk_allowed or "all")
            tooltip = (
                f"{p.name} — {p.description or '(no description)'}\n"
                f"Link: {p.link_status}  |  Admin: {'up' if p.admin_up else 'shutdown'}\n"
                f"Mode: {p.mode}  |  VLAN: {vlan_desc}\n"
                f"Speed/Duplex: {p.speed}/{p.duplex}  |  {p.port_type}"
            )
            cell.set_status(p.link_status, p.admin_up, tooltip)
