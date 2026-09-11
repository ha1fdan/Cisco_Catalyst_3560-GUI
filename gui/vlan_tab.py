from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QHeaderView, QLineEdit, QMessageBox, QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from core.models import VlanInfo

RESERVED_VLANS = {1, 1002, 1003, 1004, 1005}


class VlanEditDialog(QDialog):
    def __init__(self, parent=None, vlan_id: int | None = None, name: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Edit VLAN" if vlan_id else "Add VLAN")
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.id_spin = QSpinBox()
        self.id_spin.setRange(2, 4094)
        if vlan_id:
            self.id_spin.setValue(vlan_id)
            self.id_spin.setEnabled(False)
        form.addRow("VLAN ID:", self.id_spin)

        self.name_edit = QLineEdit(name)
        self.name_edit.setPlaceholderText("e.g. Sales")
        form.addRow("Name:", self.name_edit)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> tuple[int, str]:
        return self.id_spin.value(), self.name_edit.text().strip()


class VlanTab(QWidget):
    create_vlan_requested = Signal(int, str)
    delete_vlan_requested = Signal(int)
    rename_vlan_requested = Signal(int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._vlans: list[VlanInfo] = []

        layout = QVBoxLayout(self)

        btn_row = QHBoxLayout()
        self.add_btn = QPushButton("Add VLAN")
        self.rename_btn = QPushButton("Rename")
        self.delete_btn = QPushButton("Delete")
        self.add_btn.clicked.connect(self._on_add)
        self.rename_btn.clicked.connect(self._on_rename)
        self.delete_btn.clicked.connect(self._on_delete)
        btn_row.addWidget(self.add_btn)
        btn_row.addWidget(self.rename_btn)
        btn_row.addWidget(self.delete_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["VLAN ID", "Name", "Status", "Ports"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

    def update_vlans(self, vlans: list[VlanInfo]) -> None:
        self._vlans = vlans
        self.table.setRowCount(len(vlans))
        for row, v in enumerate(vlans):
            self.table.setItem(row, 0, QTableWidgetItem(str(v.vlan_id)))
            self.table.setItem(row, 1, QTableWidgetItem(v.name))
            self.table.setItem(row, 2, QTableWidgetItem(v.status))
            self.table.setItem(row, 3, QTableWidgetItem(", ".join(v.ports)))
        self.table.resizeColumnsToContents()

    def _selected_vlan(self) -> VlanInfo | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        return self._vlans[rows[0].row()]

    def _on_add(self) -> None:
        dlg = VlanEditDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            vlan_id, name = dlg.values()
            if vlan_id in RESERVED_VLANS:
                QMessageBox.warning(self, "Reserved VLAN", f"VLAN {vlan_id} is reserved.")
                return
            self.create_vlan_requested.emit(vlan_id, name)

    def _on_rename(self) -> None:
        vlan = self._selected_vlan()
        if vlan is None:
            QMessageBox.information(self, "No selection", "Select a VLAN first.")
            return
        dlg = VlanEditDialog(self, vlan_id=vlan.vlan_id, name=vlan.name)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            _, name = dlg.values()
            self.rename_vlan_requested.emit(vlan.vlan_id, name)

    def _on_delete(self) -> None:
        vlan = self._selected_vlan()
        if vlan is None:
            QMessageBox.information(self, "No selection", "Select a VLAN first.")
            return
        if vlan.vlan_id in RESERVED_VLANS:
            QMessageBox.warning(self, "Reserved VLAN", f"VLAN {vlan.vlan_id} cannot be deleted.")
            return
        confirm = QMessageBox.question(
            self, "Delete VLAN", f"Delete VLAN {vlan.vlan_id} ({vlan.name})?"
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.delete_vlan_requested.emit(vlan.vlan_id)
