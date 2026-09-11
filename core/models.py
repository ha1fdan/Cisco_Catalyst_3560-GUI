"""Plain data containers describing switch state, shared between core and gui."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SwitchInfo:
    hostname: str = ""
    model: str = ""
    ios_version: str = ""
    image: str = ""
    serial_number: str = ""
    mac_address: str = ""
    uptime: str = ""
    http_enabled: bool = False


@dataclass
class VlanInfo:
    vlan_id: int
    name: str
    status: str
    ports: list[str] = field(default_factory=list)


@dataclass
class PortInfo:
    name: str                       # e.g. Fa0/1
    description: str = ""
    link_status: str = "unknown"    # connected / notconnect / disabled
    admin_up: bool = True
    mode: str = "access"            # access / trunk
    access_vlan: str = "1"
    trunk_native: str = ""
    trunk_allowed: str = ""
    duplex: str = "auto"
    speed: str = "auto"
    port_type: str = ""

    @property
    def is_uplink(self) -> bool:
        return self.name.startswith(("Gi", "Te"))


@dataclass
class SviInfo:
    vlan_id: int
    name: str                       # e.g. Vlan1
    ip_address: str = ""
    subnet_mask: str = ""
    admin_up: bool = True
    protocol_up: bool = False


@dataclass
class UserAccount:
    username: str
    privilege: int = 1


@dataclass
class LineConfig:
    line: str                       # "con 0" / "vty 0 4" / "vty 5 15"
    login_method: str = "none"      # none / password / local
    has_password: bool = False
    transport: str = ""
