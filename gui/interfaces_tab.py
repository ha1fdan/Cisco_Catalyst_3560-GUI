from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QHBoxLayout,
    QHeaderView, QLineEdit, QMessageBox, QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from core.models import SviInfo


class SviEditDialog(QDialog):
    def __init__(self, parent=None, vlan_id: int | None = None, ip: str = "", mask: str = "255.255.255.0"):
        super().__init__(parent)
        self.setWindowTitle("Edit SVI" if vlan_id else "Add SVI (interface VLAN)")
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.vlan_spin = QSpinBox()
        self.vlan_spin.setRange(1, 4094)
        if vlan_id:
            self.vlan_spin.setValue(vlan_id)
            self.vlan_spin.setEnabled(False)
        form.addRow("VLAN ID:", self.vlan_spin)

        self.ip_edit = QLineEdit(ip)
        self.ip_edit.setPlaceholderText("192.168.1.1")
        form.addRow("IP Address:", self.ip_edit)

        self.mask_edit = QLineEdit(mask)
        self.mask_edit.setPlaceholderText("255.255.255.0")
        form.addRow("Subnet Mask:", self.mask_edit)

        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> tuple[int, str, str]:
        return self.vlan_spin.value(), self.ip_edit.text().strip(), self.mask_edit.text().strip()


class InterfacesTab(QWidget):
    create_svi_requested = Signal(int, str, str)
    delete_svi_requested = Signal(int)
    set_svi_admin_requested = Signal(int, bool)
    set_gateway_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._svis: list[SviInfo] = []
        self._columns_sized = False

        layout = QVBoxLayout(self)

        btn_row = QHBoxLayout()
        self.add_btn = QPushButton("Add SVI")
        self.edit_btn = QPushButton("Edit IP")
        self.toggle_btn = QPushButton("Enable/Disable")
        self.delete_btn = QPushButton("Delete")
        for b in (self.add_btn, self.edit_btn, self.toggle_btn, self.delete_btn):
            btn_row.addWidget(b)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.add_btn.clicked.connect(self._on_add)
        self.edit_btn.clicked.connect(self._on_edit)
        self.toggle_btn.clicked.connect(self._on_toggle)
        self.delete_btn.clicked.connect(self._on_delete)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Interface", "VLAN", "IP Address", "Mask", "Status"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        gw_group = QGroupBox("Default Gateway (used when this switch has no routing)")
        gw_form = QFormLayout(gw_group)
        gw_row = QHBoxLayout()
        self.gateway_edit = QLineEdit()
        self.gateway_edit.setPlaceholderText("192.168.1.254")
        gw_apply_btn = QPushButton("Apply")
        gw_apply_btn.clicked.connect(
            lambda: self.set_gateway_requested.emit(self.gateway_edit.text().strip())
        )
        gw_row.addWidget(self.gateway_edit)
        gw_row.addWidget(gw_apply_btn)
        gw_form.addRow("Gateway IP:", gw_row)
        layout.addWidget(gw_group)

    def update_svis(self, svis: list[SviInfo]) -> None:
        self._svis = svis
        self.table.setRowCount(len(svis))
        for row, s in enumerate(svis):
            status = "up" if s.admin_up else "administratively down"
            if s.admin_up:
                status += ", protocol up" if s.protocol_up else ", protocol down"
            values = [s.name, str(s.vlan_id), s.ip_address or "unassigned", s.subnet_mask, status]
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(value))
        if not self._columns_sized and svis:
            self.table.resizeColumnsToContents()
            self._columns_sized = True

    def update_gateway(self, gateway: str) -> None:
        if not self.gateway_edit.hasFocus():
            self.gateway_edit.setText(gateway)

    def _selected_svi(self) -> SviInfo | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        return self._svis[rows[0].row()]

    def _on_add(self) -> None:
        dlg = SviEditDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            vlan_id, ip, mask = dlg.values()
            if not ip or not mask:
                QMessageBox.warning(self, "Missing data", "IP address and subnet mask are required.")
                return
            self.create_svi_requested.emit(vlan_id, ip, mask)

    def _on_edit(self) -> None:
        svi = self._selected_svi()
        if svi is None:
            QMessageBox.information(self, "No selection", "Select an interface first.")
            return
        dlg = SviEditDialog(self, vlan_id=svi.vlan_id, ip=svi.ip_address,
                             mask=svi.subnet_mask or "255.255.255.0")
        if dlg.exec() == QDialog.DialogCode.Accepted:
            vlan_id, ip, mask = dlg.values()
            if not ip or not mask:
                QMessageBox.warning(self, "Missing data", "IP address and subnet mask are required.")
                return
            self.create_svi_requested.emit(vlan_id, ip, mask)

    def _on_toggle(self) -> None:
        svi = self._selected_svi()
        if svi is None:
            QMessageBox.information(self, "No selection", "Select an interface first.")
            return
        self.set_svi_admin_requested.emit(svi.vlan_id, not svi.admin_up)

    def _on_delete(self) -> None:
        svi = self._selected_svi()
        if svi is None:
            QMessageBox.information(self, "No selection", "Select an interface first.")
            return
        confirm = QMessageBox.question(self, "Delete interface", f"Delete {svi.name}?")
        if confirm == QMessageBox.StandardButton.Yes:
            self.delete_svi_requested.emit(svi.vlan_id)
