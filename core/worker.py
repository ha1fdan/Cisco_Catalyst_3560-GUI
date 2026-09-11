"""Background QThread owner of the SwitchDevice.

All slots here run in a dedicated worker thread (see gui/main_window.py,
which moves an instance of DeviceWorker into a QThread). GUI code must
never call SwitchDevice directly -- only emit requests that land on these
slots via Qt's automatic queued cross-thread connections, and react to the
result signals below.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

from .device import SwitchDevice
from .models import SwitchInfo


class DeviceWorker(QObject):
    # Connection lifecycle
    connected = Signal(object)          # SwitchInfo
    connection_failed = Signal(str)
    disconnected = Signal()
    busy = Signal(bool)
    error = Signal(str)
    action_done = Signal(str)
    config_saved = Signal()

    # State snapshots
    switch_info_updated = Signal(object)   # SwitchInfo
    vlans_updated = Signal(object)         # list[VlanInfo]
    ports_updated = Signal(object)         # list[PortInfo]
    svis_updated = Signal(object)          # list[SviInfo]
    users_updated = Signal(object)         # list[UserAccount]
    lines_updated = Signal(object)         # list[LineConfig]
    gateway_updated = Signal(str)
    running_config_updated = Signal(str)
    environment_updated = Signal(object)   # dict[str, str]

    # Terminal tab
    terminal_output = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.device = SwitchDevice()

    # ------------------------------------------------------------------
    def _run(self, fn, *args, success_msg: str | None = None, refresh: bool = True, **kwargs):
        self.busy.emit(True)
        try:
            fn(*args, **kwargs)
            if success_msg:
                self.action_done.emit(success_msg)
            if refresh:
                self._refresh_all_inner()
        except Exception as exc:  # noqa: BLE001 - surface every failure to the GUI
            self.error.emit(str(exc))
        finally:
            self.busy.emit(False)

    def _refresh_all_inner(self) -> None:
        if not self.device.connected:
            return
        info = self.device.get_switch_info()
        self.switch_info_updated.emit(info)
        self.vlans_updated.emit(self.device.get_vlans())
        running_config = self.device.get_running_config()
        self.ports_updated.emit(self.device.get_ports(running_config))
        self.svis_updated.emit(self.device.get_svis(running_config))
        self.users_updated.emit(self.device.get_local_users(running_config))
        self.lines_updated.emit(self.device.get_line_configs(running_config))
        self.gateway_updated.emit(self.device.get_default_gateway(running_config))
        self.running_config_updated.emit(running_config)
        self.environment_updated.emit(self.device.get_environment())

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------
    @Slot(str, int, str, str)
    def connect_telnet(self, host: str, port: int, password: str, secret: str) -> None:
        self.busy.emit(True)
        try:
            self.device.connect_telnet(host, password, secret, port=port)
            info: SwitchInfo = self.device.get_switch_info()
            self.connected.emit(info)
            self._refresh_all_inner()
        except Exception as exc:  # noqa: BLE001
            self.device.disconnect()
            self.connection_failed.emit(str(exc))
        finally:
            self.busy.emit(False)

    @Slot(str, int, str, str)
    def connect_serial(self, serial_port: str, baudrate: int, password: str, secret: str) -> None:
        self.busy.emit(True)
        try:
            self.device.connect_serial(serial_port, baudrate, password, secret)
            info = self.device.get_switch_info()
            self.connected.emit(info)
            self._refresh_all_inner()
        except Exception as exc:  # noqa: BLE001
            self.device.disconnect()
            self.connection_failed.emit(str(exc))
        finally:
            self.busy.emit(False)

    @Slot()
    def disconnect_device(self) -> None:
        self.device.disconnect()
        self.disconnected.emit()

    @Slot()
    def refresh_all(self) -> None:
        self.busy.emit(True)
        try:
            self._refresh_all_inner()
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))
        finally:
            self.busy.emit(False)

    # ------------------------------------------------------------------
    # VLANs
    # ------------------------------------------------------------------
    @Slot(int, str)
    def create_vlan(self, vlan_id: int, name: str) -> None:
        self._run(self.device.create_vlan, vlan_id, name, success_msg=f"VLAN {vlan_id} created")

    @Slot(int)
    def delete_vlan(self, vlan_id: int) -> None:
        self._run(self.device.delete_vlan, vlan_id, success_msg=f"VLAN {vlan_id} deleted")

    @Slot(int, str)
    def rename_vlan(self, vlan_id: int, name: str) -> None:
        self._run(self.device.rename_vlan, vlan_id, name, success_msg=f"VLAN {vlan_id} renamed")

    # ------------------------------------------------------------------
    # Ports
    # ------------------------------------------------------------------
    @Slot(str, int)
    def set_port_access(self, port_name: str, vlan_id: int) -> None:
        self._run(self.device.set_port_access, port_name, vlan_id,
                   success_msg=f"{port_name} set to access VLAN {vlan_id}")

    @Slot(str, int, str)
    def set_port_trunk(self, port_name: str, native_vlan: int, allowed_vlans: str) -> None:
        self._run(self.device.set_port_trunk, port_name,
                   native_vlan if native_vlan else None,
                   allowed_vlans if allowed_vlans else None,
                   success_msg=f"{port_name} set to trunk")

    @Slot(str, str)
    def set_port_description(self, port_name: str, description: str) -> None:
        self._run(self.device.set_port_description, port_name, description,
                   success_msg=f"{port_name} description updated")

    @Slot(str, bool)
    def set_port_admin_state(self, port_name: str, enabled: bool) -> None:
        state = "enabled" if enabled else "disabled"
        self._run(self.device.set_port_admin_state, port_name, enabled,
                   success_msg=f"{port_name} {state}")

    @Slot(str, str, str)
    def set_port_speed_duplex(self, port_name: str, speed: str, duplex: str) -> None:
        self._run(self.device.set_port_speed_duplex, port_name, speed, duplex,
                   success_msg=f"{port_name} speed/duplex updated")

    # ------------------------------------------------------------------
    # SVIs / IP
    # ------------------------------------------------------------------
    @Slot(int, str, str)
    def create_svi(self, vlan_id: int, ip: str, mask: str) -> None:
        self._run(self.device.create_svi, vlan_id, ip, mask,
                   success_msg=f"Vlan{vlan_id} interface configured")

    @Slot(int, bool)
    def set_svi_admin_state(self, vlan_id: int, enabled: bool) -> None:
        state = "enabled" if enabled else "disabled"
        self._run(self.device.set_svi_admin_state, vlan_id, enabled,
                   success_msg=f"Vlan{vlan_id} {state}")

    @Slot(int)
    def delete_svi(self, vlan_id: int) -> None:
        self._run(self.device.delete_svi, vlan_id, success_msg=f"Vlan{vlan_id} interface removed")

    @Slot(str)
    def set_default_gateway(self, ip: str) -> None:
        self._run(self.device.set_default_gateway, ip, success_msg="Default gateway updated")

    # ------------------------------------------------------------------
    # Security
    # ------------------------------------------------------------------
    @Slot(str)
    def set_hostname(self, name: str) -> None:
        self._run(self.device.set_hostname, name, success_msg=f"Hostname set to {name}")

    @Slot(str)
    def set_enable_secret(self, secret: str) -> None:
        self._run(self.device.set_enable_secret, secret, success_msg="Enable secret updated")

    @Slot(str, str)
    def set_line_password(self, line: str, password: str) -> None:
        self._run(self.device.set_line_password, line, password,
                   success_msg=f"Password updated for line {line}")

    @Slot(bool)
    def set_http_server(self, enabled: bool) -> None:
        state = "enabled" if enabled else "disabled"
        self._run(self.device.set_http_server, enabled, success_msg=f"HTTP server {state}")

    @Slot(str, str, int)
    def add_local_user(self, username: str, password: str, privilege: int) -> None:
        self._run(self.device.add_local_user, username, password, privilege,
                   success_msg=f"User {username} added")

    @Slot(str)
    def delete_local_user(self, username: str) -> None:
        self._run(self.device.delete_local_user, username, success_msg=f"User {username} removed")

    # ------------------------------------------------------------------
    # Maintenance / raw terminal
    # ------------------------------------------------------------------
    @Slot()
    def save_config(self) -> None:
        self.busy.emit(True)
        try:
            self.device.save_config()
            self.config_saved.emit()
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))
        finally:
            self.busy.emit(False)

    @Slot(str)
    def send_exec_command(self, command: str) -> None:
        self.busy.emit(True)
        try:
            output = self.device.send_exec(command)
            self.terminal_output.emit(output)
        except Exception as exc:  # noqa: BLE001
            self.terminal_output.emit(f"ERROR: {exc}")
        finally:
            self.busy.emit(False)
