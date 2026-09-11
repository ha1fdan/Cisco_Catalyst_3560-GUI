from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QHBoxLayout, QHeaderView, QLineEdit, QPushButton, QStackedWidget, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from core.models import PortInfo, VlanInfo

SPEED_OPTIONS = ["auto", "10", "100", "1000"]
DUPLEX_OPTIONS = ["auto", "half", "full"]


class PortEditDialog(QDialog):
    def __init__(self, parent, port: PortInfo, vlans: list[VlanInfo]):
        super().__init__(parent)
        self.port = port
        self.setWindowTitle(f"Configure {port.name}")
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.desc_edit = QLineEdit(port.description)
        form.addRow("Description:", self.desc_edit)

        self.enabled_check = QCheckBox("Port enabled (no shutdown)")
        self.enabled_check.setChecked(port.admin_up)
        form.addRow("Admin State:", self.enabled_check)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["access", "trunk"])
        self.mode_combo.setCurrentText(port.mode)
        form.addRow("Mode:", self.mode_combo)

        self.stack = QStackedWidget()

        access_page = QWidget()
        access_form = QFormLayout(access_page)
        self.vlan_combo = QComboBox()
        selectable = [v for v in vlans if v.vlan_id not in (1002, 1003, 1004, 1005)]
        for v in selectable:
            self.vlan_combo.addItem(f"{v.vlan_id} - {v.name}", v.vlan_id)
        idx = self.vlan_combo.findData(int(port.access_vlan) if port.access_vlan.isdigit() else 1)
        if idx >= 0:
            self.vlan_combo.setCurrentIndex(idx)
        access_form.addRow("Access VLAN:", self.vlan_combo)
        self.stack.addWidget(access_page)

        trunk_page = QWidget()
        trunk_form = QFormLayout(trunk_page)
        self.native_edit = QLineEdit(port.trunk_native)
        self.native_edit.setPlaceholderText("e.g. 1 (blank = default)")
        self.allowed_edit = QLineEdit(port.trunk_allowed)
        self.allowed_edit.setPlaceholderText("e.g. 10,20,30 (blank = all)")
        trunk_form.addRow("Native VLAN:", self.native_edit)
        trunk_form.addRow("Allowed VLANs:", self.allowed_edit)
        self.stack.addWidget(trunk_page)

        self.stack.setCurrentIndex(0 if port.mode == "access" else 1)
        self.mode_combo.currentTextChanged.connect(
            lambda text: self.stack.setCurrentIndex(0 if text == "access" else 1)
        )
        form.addRow(self.stack)

        self.speed_combo = QComboBox()
        self.speed_combo.addItems(SPEED_OPTIONS)
        self.speed_combo.setCurrentText(port.speed if port.speed in SPEED_OPTIONS else "auto")
        form.addRow("Speed:", self.speed_combo)

        self.duplex_combo = QComboBox()
        self.duplex_combo.addItems(DUPLEX_OPTIONS)
        self.duplex_combo.setCurrentText(port.duplex if port.duplex in DUPLEX_OPTIONS else "auto")
        form.addRow("Duplex:", self.duplex_combo)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class PortsTab(QWidget):
    set_port_access_requested = Signal(str, int)
    set_port_trunk_requested = Signal(str, int, str)
    set_port_description_requested = Signal(str, str)
    set_port_admin_state_requested = Signal(str, bool)
    set_port_speed_duplex_requested = Signal(str, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ports: list[PortInfo] = []
        self._vlans: list[VlanInfo] = []
        self._columns_sized = False

        layout = QVBoxLayout(self)
        btn_row = QHBoxLayout()
        self.edit_btn = QPushButton("Configure Selected Port…")
        self.edit_btn.clicked.connect(self._on_edit)
        btn_row.addWidget(self.edit_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            ["Port", "Link", "Admin", "Description", "Mode", "VLAN", "Speed", "Duplex", "Type"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.doubleClicked.connect(lambda _: self._on_edit())
        layout.addWidget(self.table)

    def update_ports(self, ports: list[PortInfo]) -> None:
        self._ports = ports
        self.table.setRowCount(len(ports))
        for row, p in enumerate(ports):
            vlan_desc = p.access_vlan if p.mode == "access" else (p.trunk_allowed or "all")
            values = [
                p.name, p.link_status, "up" if p.admin_up else "shutdown",
                p.description, p.mode, vlan_desc, p.speed, p.duplex, p.port_type,
            ]
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(value))
        if not self._columns_sized and ports:
            self.table.resizeColumnsToContents()
            self._columns_sized = True

    def update_vlans(self, vlans: list[VlanInfo]) -> None:
        self._vlans = vlans

    def select_port(self, port_name: str) -> None:
        for row, p in enumerate(self._ports):
            if p.name == port_name:
                self.table.selectRow(row)
                self._on_edit()
                return

    def _selected_port(self) -> PortInfo | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        return self._ports[rows[0].row()]

    def _on_edit(self) -> None:
        port = self._selected_port()
        if port is None:
            return
        dlg = PortEditDialog(self, port, self._vlans)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        name = port.name
        if dlg.desc_edit.text().strip() != port.description:
            self.set_port_description_requested.emit(name, dlg.desc_edit.text().strip())

        if dlg.enabled_check.isChecked() != port.admin_up:
            self.set_port_admin_state_requested.emit(name, dlg.enabled_check.isChecked())

        if dlg.mode_combo.currentText() == "access":
            vlan_id = dlg.vlan_combo.currentData()
            if vlan_id is not None:
                self.set_port_access_requested.emit(name, int(vlan_id))
        else:
            native_text = dlg.native_edit.text().strip()
            native_vlan = int(native_text) if native_text.isdigit() else 0
            allowed = dlg.allowed_edit.text().strip()
            self.set_port_trunk_requested.emit(name, native_vlan, allowed)

        speed, duplex = dlg.speed_combo.currentText(), dlg.duplex_combo.currentText()
        if speed != port.speed or duplex != port.duplex:
            self.set_port_speed_duplex_requested.emit(name, speed, duplex)
