from __future__ import annotations

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QLabel, QMainWindow, QMessageBox, QSpinBox, QStatusBar,
    QTabWidget, QToolBar, QWidget,
)

from core.models import SwitchInfo
from core.worker import DeviceWorker
from .connection_dialog import ConnectionDialog
from .dashboard_tab import DashboardTab
from .interfaces_tab import InterfacesTab
from .ports_tab import PortsTab
from .security_tab import SecurityTab
from .terminal_tab import TerminalTab
from .vlan_tab import VlanTab


class MainWindow(QMainWindow):
    # Bridging signals -> DeviceWorker slots (cross-thread, auto-queued by Qt).
    # Every call into the worker MUST go through a real Signal connected to a
    # bound method of a QObject -- Qt can only auto-detect cross-thread
    # delivery via the receiving QObject's thread affinity. A lambda or a
    # direct method call has no such affinity to inspect: it either runs
    # synchronously on the caller's thread (freezing the GUI while Netmiko
    # blocks on I/O) or, for QTimer-touching code, aborts with
    # "QBasicTimer::start: Timers cannot be started from another thread".
    request_connect_telnet = Signal(str, int, str, str)
    request_connect_serial = Signal(str, int, str, str)
    request_save_config = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Cisco Catalyst 3560 GUI — not connected")
        self.resize(1080, 720)

        # --- worker thread setup ---
        self.thread = QThread(self)
        self.worker = DeviceWorker()
        self.worker.moveToThread(self.thread)
        self.thread.start()

        # --- tabs ---
        self.dashboard_tab = DashboardTab()
        self.vlan_tab = VlanTab()
        self.ports_tab = PortsTab()
        self.interfaces_tab = InterfacesTab()
        self.security_tab = SecurityTab()
        self.terminal_tab = TerminalTab()

        self.tabs = QTabWidget()
        self.tabs.addTab(self.dashboard_tab, "Dashboard")
        self.tabs.addTab(self.vlan_tab, "VLANs")
        self.tabs.addTab(self.ports_tab, "Ports")
        self.tabs.addTab(self.interfaces_tab, "Interfaces / IP")
        self.tabs.addTab(self.security_tab, "Security / Users")
        self.tabs.addTab(self.terminal_tab, "Terminal")
        self.setCentralWidget(self.tabs)
        self.tabs.setEnabled(False)

        self._build_toolbar()
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Not connected")

        self._wire_worker_signals()
        self._wire_tab_signals()

        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(20_000)
        self.refresh_timer.timeout.connect(self.worker.refresh_all)

    # ------------------------------------------------------------------
    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        self.action_connect = toolbar.addAction("Connect…")
        self.action_connect.triggered.connect(self.show_connect_dialog)

        self.action_disconnect = toolbar.addAction("Disconnect")
        self.action_disconnect.triggered.connect(self.worker.disconnect_device)
        self.action_disconnect.setEnabled(False)

        toolbar.addSeparator()

        self.action_refresh = toolbar.addAction("Refresh")
        self.action_refresh.triggered.connect(self.worker.refresh_all)
        self.action_refresh.setEnabled(False)

        self.action_save = toolbar.addAction("Save to Startup-Config")
        self.action_save.triggered.connect(self._on_save_clicked)
        self.action_save.setEnabled(False)

        toolbar.addSeparator()

        self.autorefresh_check = QCheckBox("Auto-refresh every")
        self.autorefresh_check.setChecked(True)
        self.autorefresh_check.toggled.connect(self._on_autorefresh_toggled)
        toolbar.addWidget(self.autorefresh_check)

        self.autorefresh_spin = QSpinBox()
        self.autorefresh_spin.setRange(5, 300)
        self.autorefresh_spin.setValue(20)
        self.autorefresh_spin.setSuffix("s")
        self.autorefresh_spin.valueChanged.connect(
            lambda v: self.refresh_timer.setInterval(v * 1000)
        )
        toolbar.addWidget(self.autorefresh_spin)

        self.busy_label = QLabel("")
        self.busy_label.setStyleSheet("color: #f59e0b; font-weight: 600; padding-left: 10px;")
        toolbar.addWidget(self.busy_label)

    def _on_autorefresh_toggled(self, checked: bool) -> None:
        if checked and self.thread.isRunning() and self.action_refresh.isEnabled():
            self.refresh_timer.start()
        else:
            self.refresh_timer.stop()

    def _on_save_clicked(self) -> None:
        confirm = QMessageBox.question(
            self, "Save configuration",
            "Write the running configuration to startup-config on the switch?"
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.request_save_config.emit()

    # ------------------------------------------------------------------
    def _wire_worker_signals(self) -> None:
        w = self.worker
        w.connected.connect(self._on_connected)
        w.connection_failed.connect(self._on_connection_failed)
        w.disconnected.connect(self._on_disconnected)
        w.busy.connect(self._on_busy)
        w.error.connect(self._on_error)
        w.action_done.connect(self._on_action_done)
        w.config_saved.connect(self._on_config_saved)

        w.switch_info_updated.connect(self._on_switch_info)
        w.vlans_updated.connect(self.vlan_tab.update_vlans)
        w.vlans_updated.connect(self.ports_tab.update_vlans)
        w.ports_updated.connect(self.ports_tab.update_ports)
        w.ports_updated.connect(self.dashboard_tab.update_ports)
        w.svis_updated.connect(self.interfaces_tab.update_svis)
        w.users_updated.connect(self.security_tab.update_users)
        w.lines_updated.connect(self.security_tab.update_lines)
        w.gateway_updated.connect(self.interfaces_tab.update_gateway)
        w.environment_updated.connect(self.dashboard_tab.update_environment)
        w.terminal_output.connect(self.terminal_tab.append_output)

        self.request_connect_telnet.connect(w.connect_telnet)
        self.request_connect_serial.connect(w.connect_serial)
        self.request_save_config.connect(w.save_config)

    def _wire_tab_signals(self) -> None:
        w = self.worker

        self.dashboard_tab.port_selected.connect(self._on_port_selected)

        self.vlan_tab.create_vlan_requested.connect(w.create_vlan)
        self.vlan_tab.delete_vlan_requested.connect(w.delete_vlan)
        self.vlan_tab.rename_vlan_requested.connect(w.rename_vlan)

        self.ports_tab.set_port_access_requested.connect(w.set_port_access)
        self.ports_tab.set_port_trunk_requested.connect(w.set_port_trunk)
        self.ports_tab.set_port_description_requested.connect(w.set_port_description)
        self.ports_tab.set_port_admin_state_requested.connect(w.set_port_admin_state)
        self.ports_tab.set_port_speed_duplex_requested.connect(w.set_port_speed_duplex)

        self.interfaces_tab.create_svi_requested.connect(w.create_svi)
        self.interfaces_tab.delete_svi_requested.connect(w.delete_svi)
        self.interfaces_tab.set_svi_admin_requested.connect(w.set_svi_admin_state)
        self.interfaces_tab.set_gateway_requested.connect(w.set_default_gateway)

        self.security_tab.set_hostname_requested.connect(w.set_hostname)
        self.security_tab.set_enable_secret_requested.connect(w.set_enable_secret)
        self.security_tab.set_line_password_requested.connect(w.set_line_password)
        self.security_tab.set_http_server_requested.connect(w.set_http_server)
        self.security_tab.add_user_requested.connect(w.add_local_user)
        self.security_tab.delete_user_requested.connect(w.delete_local_user)

        self.terminal_tab.command_submitted.connect(w.send_exec_command)

    def _on_port_selected(self, port_name: str) -> None:
        self.tabs.setCurrentWidget(self.ports_tab)
        self.ports_tab.select_port(port_name)

    # ------------------------------------------------------------------
    def show_connect_dialog(self) -> None:
        dlg = ConnectionDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        params = dlg.result_params()
        if params is None:
            return
        self.status_bar.showMessage("Connecting…")
        if params.mode == "telnet":
            self.request_connect_telnet.emit(params.host, params.port, params.password, params.secret)
        else:
            self.request_connect_serial.emit(
                params.serial_port, params.baudrate, params.password, params.secret
            )

    def _on_connected(self, info: SwitchInfo) -> None:
        self.setWindowTitle(f"Cisco Catalyst 3560 GUI — {info.hostname}")
        self.status_bar.showMessage(f"Connected to {info.hostname}", 5000)
        self.tabs.setEnabled(True)
        self.action_connect.setEnabled(False)
        self.action_disconnect.setEnabled(True)
        self.action_refresh.setEnabled(True)
        self.action_save.setEnabled(True)
        if self.autorefresh_check.isChecked():
            self.refresh_timer.start()

    def _on_connection_failed(self, message: str) -> None:
        self.status_bar.showMessage("Connection failed", 5000)
        QMessageBox.critical(self, "Connection failed", message)

    def _on_disconnected(self) -> None:
        self.setWindowTitle("Cisco Catalyst 3560 GUI — not connected")
        self.status_bar.showMessage("Disconnected", 5000)
        self.tabs.setEnabled(False)
        self.action_connect.setEnabled(True)
        self.action_disconnect.setEnabled(False)
        self.action_refresh.setEnabled(False)
        self.action_save.setEnabled(False)
        self.refresh_timer.stop()

    def _on_busy(self, busy: bool) -> None:
        self.busy_label.setText("Working…" if busy else "")

    def _on_action_done(self, message: str) -> None:
        self.status_bar.showMessage(message, 4000)

    def _on_config_saved(self) -> None:
        self.status_bar.showMessage("Configuration saved to startup-config.", 5000)

    def _on_error(self, message: str) -> None:
        self.status_bar.showMessage("Error — see dialog", 5000)
        QMessageBox.warning(self, "Switch error", message)

    def _on_switch_info(self, info: SwitchInfo) -> None:
        self.setWindowTitle(f"Cisco Catalyst 3560 GUI — {info.hostname}")
        self.dashboard_tab.update_switch_info(info)
        self.security_tab.update_hostname(info.hostname)
        self.security_tab.update_http(info.http_enabled)

    # ------------------------------------------------------------------
    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self.refresh_timer.stop()
        self.worker.device.disconnect()
        self.thread.quit()
        self.thread.wait(3000)
        super().closeEvent(event)
