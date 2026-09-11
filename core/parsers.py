"""Parsers turning raw Cisco IOS CLI text into the dataclasses in models.py.

All parsing is done with plain regex/string splitting against the exact
output format of a Catalyst 3560 running IOS 12.2(46)SE (IP Base image).
No TextFSM/genie dependency, so it stays lightweight and predictable.
"""
from __future__ import annotations

import re

from .models import LineConfig, PortInfo, SviInfo, SwitchInfo, UserAccount, VlanInfo


def _columns(header_line: str, columns: list[str]) -> list[tuple[str, int]]:
    """Locate each column name's start offset in a fixed-width table header."""
    positions = [(col, header_line.index(col)) for col in columns]
    positions.sort(key=lambda pair: pair[1])
    return positions


def _split_row(line: str, positions: list[tuple[str, int]]) -> dict[str, str]:
    row = {}
    for i, (col, start) in enumerate(positions):
        end = positions[i + 1][1] if i + 1 < len(positions) else len(line)
        row[col] = line[start:end].strip()
    return row


def parse_table(output: str, columns: list[str]) -> list[dict[str, str]]:
    """Generic parser for Cisco's fixed-width 'show' tables."""
    lines = output.splitlines()
    header_idx = None
    for i, line in enumerate(lines):
        if columns[0] in line and all(c in line for c in columns):
            header_idx = i
            break
    if header_idx is None:
        return []
    positions = _columns(lines[header_idx], columns)
    rows = []
    for line in lines[header_idx + 1:]:
        if not line.strip():
            continue
        rows.append(_split_row(line, positions))
    return rows


def parse_vlan_brief(output: str) -> list[VlanInfo]:
    vlans = []
    for line in output.splitlines():
        line = line.rstrip()
        if not line or line.startswith("VLAN") or line.startswith("----"):
            continue
        m = re.match(r"^(\d+)\s+(.*)$", line)
        if not m:
            continue
        vlan_id = int(m.group(1))
        parts = re.split(r"\s{2,}", m.group(2).strip())
        name = parts[0] if len(parts) > 0 else ""
        status = parts[1] if len(parts) > 1 else ""
        ports_str = parts[2] if len(parts) > 2 else ""
        ports = [p.strip() for p in ports_str.split(",") if p.strip()]
        vlans.append(VlanInfo(vlan_id=vlan_id, name=name, status=status, ports=ports))
    return vlans


def parse_interfaces_status(output: str) -> dict[str, dict[str, str]]:
    """Returns {port_name: {Status, Vlan, Duplex, Speed, Type, Name}}."""
    rows = parse_table(output, ["Port", "Name", "Status", "Vlan", "Duplex", "Speed", "Type"])
    return {row["Port"]: row for row in rows if row.get("Port")}


def parse_ip_interface_brief(output: str) -> dict[str, dict[str, str]]:
    """Returns {interface_name: {IP-Address, Status, Protocol}}."""
    rows = parse_table(output, ["Interface", "IP-Address", "OK?", "Method", "Status", "Protocol"])
    return {row["Interface"]: row for row in rows if row.get("Interface")}


def parse_interface_blocks(running_config: str) -> dict[str, list[str]]:
    """Split 'show running-config' into {interface_name: [config lines]}."""
    blocks: dict[str, list[str]] = {}
    current: str | None = None
    acc: list[str] = []
    for line in running_config.splitlines():
        m = re.match(r"^interface (\S+)\s*$", line)
        if m:
            if current is not None:
                blocks[current] = acc
            current = m.group(1)
            acc = []
            continue
        if current is not None:
            if line.strip() == "!":
                blocks[current] = acc
                current = None
                acc = []
            else:
                acc.append(line.strip())
    if current is not None:
        blocks[current] = acc
    return blocks


_SHORT_TO_LONG = {
    "Fa": "FastEthernet",
    "Gi": "GigabitEthernet",
    "Te": "TenGigabitEthernet",
    "Vl": "Vlan",
}


def expand_interface_name(short: str) -> str:
    """'Fa0/1' -> 'FastEthernet0/1', 'Gi0/1' -> 'GigabitEthernet0/1'."""
    m = re.match(r"^([A-Za-z]{2})(\d.*)$", short)
    if not m:
        return short
    prefix, rest = m.group(1), m.group(2)
    return _SHORT_TO_LONG.get(prefix, short) + rest


def shorten_interface_name(long: str) -> str:
    for short, full in _SHORT_TO_LONG.items():
        if long.startswith(full):
            return short + long[len(full):]
    return long


def parse_ports(status_output: str, running_config: str) -> list[PortInfo]:
    status_rows = parse_interfaces_status(status_output)
    iface_blocks = parse_interface_blocks(running_config)

    ports = []
    for short_name, row in status_rows.items():
        full_name = expand_interface_name(short_name)
        block = iface_blocks.get(full_name, [])
        block_text = "\n".join(block)

        description = ""
        m = re.search(r"^description (.+)$", block_text, re.M)
        if m:
            description = m.group(1).strip()
        if not description:
            description = row.get("Name", "")

        admin_up = "shutdown" not in [l.strip() for l in block]

        mode = "trunk" if "switchport mode trunk" in block_text else "access"
        if row.get("Vlan", "").lower() == "trunk":
            mode = "trunk"

        access_vlan = row.get("Vlan", "1")
        m = re.search(r"^switchport access vlan (\d+)$", block_text, re.M)
        if m:
            access_vlan = m.group(1)

        trunk_native = ""
        m = re.search(r"^switchport trunk native vlan (\d+)$", block_text, re.M)
        if m:
            trunk_native = m.group(1)

        trunk_allowed = ""
        m = re.search(r"^switchport trunk allowed vlan (?:add )?(.+)$", block_text, re.M)
        if m:
            trunk_allowed = m.group(1).strip()

        def _strip_auto_prefix(value: str) -> str:
            value = value.strip() or "auto"
            return value[2:] if value.startswith("a-") else value

        speed = _strip_auto_prefix(row.get("Speed", "auto"))
        duplex = _strip_auto_prefix(row.get("Duplex", "auto"))
        m = re.search(r"^speed (\S+)$", block_text, re.M)
        if m:
            speed = m.group(1)
        m = re.search(r"^duplex (\S+)$", block_text, re.M)
        if m:
            duplex = m.group(1)

        ports.append(PortInfo(
            name=short_name,
            description=description,
            link_status=row.get("Status", "unknown"),
            admin_up=admin_up,
            mode=mode,
            access_vlan=access_vlan,
            trunk_native=trunk_native,
            trunk_allowed=trunk_allowed,
            duplex=duplex,
            speed=speed,
            port_type=row.get("Type", ""),
        ))

    # Keep physical port ordering (Fa before Gi, numeric within each).
    def sort_key(p: PortInfo):
        m = re.match(r"^([A-Za-z]+)(\d+)/(\d+)$", p.name)
        if not m:
            return (99, 0, 0)
        prefix_rank = 0 if m.group(1) == "Fa" else 1
        return (prefix_rank, int(m.group(2)), int(m.group(3)))

    ports.sort(key=sort_key)
    return ports


def parse_svis(ip_brief_output: str, running_config: str) -> list[SviInfo]:
    ip_rows = parse_ip_interface_brief(ip_brief_output)
    iface_blocks = parse_interface_blocks(running_config)

    svis = []
    for name, row in ip_rows.items():
        if not name.startswith("Vlan"):
            continue
        vlan_id = int(re.sub(r"\D", "", name) or 0)
        block = iface_blocks.get(name, [])
        block_text = "\n".join(block)

        mask = ""
        m = re.search(r"^ip address (\S+) (\S+)$", block_text, re.M)
        ip_addr = row.get("IP-Address", "")
        if m:
            ip_addr = m.group(1)
            mask = m.group(2)
        if ip_addr == "unassigned":
            ip_addr = ""

        admin_up = "shutdown" not in [l.strip() for l in block]

        svis.append(SviInfo(
            vlan_id=vlan_id,
            name=name,
            ip_address=ip_addr,
            subnet_mask=mask,
            admin_up=admin_up,
            protocol_up=row.get("Protocol", "").lower() == "up",
        ))
    svis.sort(key=lambda s: s.vlan_id)
    return svis


def parse_switch_info(version_output: str, http_status_output: str = "") -> SwitchInfo:
    info = SwitchInfo()

    m = re.search(r"^(\S+) uptime is (.+)$", version_output, re.M)
    if m:
        info.hostname = m.group(1)
        info.uptime = m.group(2)

    m = re.search(r"Version (\S+?),", version_output)
    if m:
        info.ios_version = m.group(1)

    m = re.search(r"^cisco (\S+) \(", version_output, re.M)
    if m:
        info.model = m.group(1)

    m = re.search(r'System image file is "(.+)"', version_output)
    if m:
        info.image = m.group(1)

    m = re.search(r"System serial number\s*:\s*(\S+)", version_output)
    if not m:
        m = re.search(r"Processor board ID\s+(\S+)", version_output)
    if m:
        info.serial_number = m.group(1)

    m = re.search(r"Base ethernet MAC Address\s*:\s*(\S+)", version_output)
    if m:
        info.mac_address = m.group(1)

    if "HTTP server status: Enabled" in http_status_output:
        info.http_enabled = True

    return info


def parse_local_users(running_config: str) -> list[UserAccount]:
    users = []
    for m in re.finditer(
        r"^username (\S+)(?: privilege (\d+))? (?:secret|password)\b", running_config, re.M
    ):
        username = m.group(1)
        privilege = int(m.group(2)) if m.group(2) else 1
        users.append(UserAccount(username=username, privilege=privilege))
    return users


def parse_line_configs(running_config: str) -> list[LineConfig]:
    lines = []
    for line_id in ("con 0", "vty 0 4", "vty 5 15"):
        m = re.search(rf"^line {re.escape(line_id)}\n((?:.*\n)*?)(?=^line |\Z)", running_config, re.M)
        block = m.group(1) if m else ""
        has_password = bool(re.search(r"^\s*password\b", block, re.M))
        login_method = "none"
        if re.search(r"^\s*login local\s*$", block, re.M):
            login_method = "local"
        elif re.search(r"^\s*login\s*$", block, re.M):
            login_method = "password"
        transport = ""
        m2 = re.search(r"^\s*transport input (.+)$", block, re.M)
        if m2:
            transport = m2.group(1).strip()
        lines.append(LineConfig(line=line_id, login_method=login_method,
                                 has_password=has_password, transport=transport))
    return lines


def parse_default_gateway(running_config: str) -> str:
    m = re.search(r"^ip default-gateway (\S+)$", running_config, re.M)
    return m.group(1) if m else ""


def parse_environment(show_env_output: str) -> dict[str, str]:
    env = {"fan": "unknown", "temperature": "unknown"}
    m = re.search(r"FAN is (\S+)", show_env_output)
    if m:
        env["fan"] = m.group(1)
    m = re.search(r"TEMPERATURE is (\S+)", show_env_output)
    if m:
        env["temperature"] = m.group(1)
    return env
