"""Thin synchronous wrapper around Netmiko for talking to a Catalyst 3560.

This class does blocking network/serial I/O -- it must only ever be called
from the background thread owned by core.worker.DeviceWorker, never from
the Qt GUI thread.
"""
from __future__ import annotations

from netmiko import ConnectHandler
from netmiko.base_connection import BaseConnection

from . import parsers
from .models import LineConfig, PortInfo, SviInfo, SwitchInfo, UserAccount, VlanInfo


class SwitchDevice:
    def __init__(self) -> None:
        self._conn: BaseConnection | None = None

    @property
    def connected(self) -> bool:
        return self._conn is not None

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------
    def connect_telnet(self, host: str, password: str, secret: str,
                        port: int = 23, timeout: float = 10) -> None:
        self._conn = ConnectHandler(
            device_type="cisco_ios_telnet",
            host=host,
            port=port,
            password=password,
            secret=secret,
            conn_timeout=timeout,
            timeout=timeout,
            fast_cli=False,
        )
        self._conn.enable()

    def connect_serial(self, serial_port: str, baudrate: int, password: str,
                        secret: str, timeout: float = 10) -> None:
        self._conn = ConnectHandler(
            device_type="cisco_ios_serial",
            host="",
            password=password,
            secret=secret,
            serial_settings={
                "port": serial_port,
                "baudrate": baudrate,
                "bytesize": 8,
                "parity": "N",
                "stopbits": 1,
            },
            conn_timeout=timeout,
            timeout=timeout,
            fast_cli=False,
        )
        self._conn.enable()

    def disconnect(self) -> None:
        if self._conn is not None:
            try:
                self._conn.disconnect()
            except Exception:
                pass
            self._conn = None

    def _require(self) -> BaseConnection:
        if self._conn is None:
            raise RuntimeError("Not connected to a switch")
        return self._conn

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------
    def get_running_config(self) -> str:
        return self._require().send_command("show running-config", read_timeout=20)

    def get_http_status_raw(self) -> str:
        return self._require().send_command("show ip http server status", read_timeout=10)

    def get_switch_info(self) -> SwitchInfo:
        conn = self._require()
        version = conn.send_command("show version", read_timeout=20)
        http_status = conn.send_command("show ip http server status", read_timeout=10)
        return parsers.parse_switch_info(version, http_status)

    def get_vlans(self) -> list[VlanInfo]:
        output = self._require().send_command("show vlan brief", read_timeout=15)
        return parsers.parse_vlan_brief(output)

    def get_ports(self, running_config: str | None = None) -> list[PortInfo]:
        conn = self._require()
        status = conn.send_command("show interfaces status", read_timeout=15)
        if running_config is None:
            running_config = self.get_running_config()
        return parsers.parse_ports(status, running_config)

    def get_svis(self, running_config: str | None = None) -> list[SviInfo]:
        conn = self._require()
        ip_brief = conn.send_command("show ip interface brief", read_timeout=15)
        if running_config is None:
            running_config = self.get_running_config()
        return parsers.parse_svis(ip_brief, running_config)

    def get_local_users(self, running_config: str | None = None) -> list[UserAccount]:
        if running_config is None:
            running_config = self.get_running_config()
        return parsers.parse_local_users(running_config)

    def get_line_configs(self, running_config: str | None = None) -> list[LineConfig]:
        if running_config is None:
            running_config = self.get_running_config()
        return parsers.parse_line_configs(running_config)

    def get_default_gateway(self, running_config: str | None = None) -> str:
        if running_config is None:
            running_config = self.get_running_config()
        return parsers.parse_default_gateway(running_config)

    def get_environment(self) -> dict[str, str]:
        output = self._require().send_command("show env all", read_timeout=10)
        return parsers.parse_environment(output)

    # ------------------------------------------------------------------
    # VLAN actions
    # ------------------------------------------------------------------
    def create_vlan(self, vlan_id: int, name: str = "") -> None:
        cmds = [f"vlan {vlan_id}"]
        if name:
            cmds.append(f"name {name}")
        self._require().send_config_set(cmds)

    def delete_vlan(self, vlan_id: int) -> None:
        self._require().send_config_set([f"no vlan {vlan_id}"])

    def rename_vlan(self, vlan_id: int, name: str) -> None:
        self._require().send_config_set([f"vlan {vlan_id}", f"name {name}"])

    # ------------------------------------------------------------------
    # Port actions
    # ------------------------------------------------------------------
    def set_port_access(self, port_name: str, vlan_id: int) -> None:
        full = parsers.expand_interface_name(port_name)
        self._require().send_config_set([
            f"interface {full}",
            "switchport mode access",
            f"switchport access vlan {vlan_id}",
        ])

    def set_port_trunk(self, port_name: str, native_vlan: int | None = None,
                        allowed_vlans: str | None = None) -> None:
        full = parsers.expand_interface_name(port_name)
        cmds = [f"interface {full}", "switchport trunk encapsulation dot1q", "switchport mode trunk"]
        if native_vlan is not None:
            cmds.append(f"switchport trunk native vlan {native_vlan}")
        if allowed_vlans:
            cmds.append(f"switchport trunk allowed vlan {allowed_vlans}")
        self._require().send_config_set(cmds)

    def set_port_description(self, port_name: str, description: str) -> None:
        full = parsers.expand_interface_name(port_name)
        if description:
            self._require().send_config_set([f"interface {full}", f"description {description}"])
        else:
            self._require().send_config_set([f"interface {full}", "no description"])

    def set_port_admin_state(self, port_name: str, enabled: bool) -> None:
        full = parsers.expand_interface_name(port_name)
        cmd = "no shutdown" if enabled else "shutdown"
        self._require().send_config_set([f"interface {full}", cmd])

    def set_port_speed_duplex(self, port_name: str, speed: str, duplex: str) -> None:
        full = parsers.expand_interface_name(port_name)
        self._require().send_config_set([
            f"interface {full}",
            f"speed {speed}",
            f"duplex {duplex}",
        ])

    # ------------------------------------------------------------------
    # SVI / IP actions
    # ------------------------------------------------------------------
    def create_svi(self, vlan_id: int, ip: str, mask: str) -> None:
        self._require().send_config_set([
            f"interface vlan {vlan_id}",
            f"ip address {ip} {mask}",
            "no shutdown",
        ])

    def set_svi_ip(self, vlan_id: int, ip: str, mask: str) -> None:
        self.create_svi(vlan_id, ip, mask)

    def set_svi_admin_state(self, vlan_id: int, enabled: bool) -> None:
        cmd = "no shutdown" if enabled else "shutdown"
        self._require().send_config_set([f"interface vlan {vlan_id}", cmd])

    def delete_svi(self, vlan_id: int) -> None:
        self._require().send_config_set([f"no interface vlan {vlan_id}"])

    def set_default_gateway(self, ip: str) -> None:
        self._require().send_config_set([f"ip default-gateway {ip}"])

    # ------------------------------------------------------------------
    # Security / identity actions
    # ------------------------------------------------------------------
    def set_hostname(self, name: str) -> None:
        self._require().send_config_set([f"hostname {name}"])

    def set_enable_secret(self, secret: str) -> None:
        self._require().send_config_set([f"enable secret {secret}"])

    def set_line_password(self, line: str, password: str) -> None:
        """line is one of: 'con 0', 'vty 0 4', 'vty 5 15'."""
        self._require().send_config_set([f"line {line}", f"password {password}", "login"])

    def set_http_server(self, enabled: bool) -> None:
        cmd = "ip http server" if enabled else "no ip http server"
        self._require().send_config_set([cmd])

    def add_local_user(self, username: str, password: str, privilege: int = 15) -> None:
        self._require().send_config_set([
            f"username {username} privilege {privilege} secret {password}"
        ])

    def delete_local_user(self, username: str) -> None:
        self._require().send_config_set([f"no username {username}"])

    # ------------------------------------------------------------------
    # Raw / maintenance
    # ------------------------------------------------------------------
    def send_exec(self, command: str) -> str:
        return self._require().send_command_timing(
            command, strip_prompt=False, strip_command=False
        )

    def send_config_lines(self, commands: list[str]) -> str:
        return self._require().send_config_set(commands)

    def save_config(self) -> None:
        self._require().save_config()
