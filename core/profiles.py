"""Persisted device connection profiles.

Stored as JSON in the user's config directory (~/.config/cisco3560-gui by
default, respecting $XDG_CONFIG_HOME). Includes password/enable secret in
plaintext by deliberate choice -- this is a personal lab tool, and the
file is chmod'd 0600 (owner read/write only) after every save so at least
other local users/processes without root can't casually read it. It is
never part of the git repo; nothing here should ever be committed.
"""
from __future__ import annotations

import json
import os
import stat
from dataclasses import asdict, dataclass, field
from pathlib import Path


def _config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    return Path(base) / "cisco3560-gui"


def _profiles_path() -> Path:
    return _config_dir() / "devices.json"


@dataclass
class DeviceProfile:
    name: str
    mode: str                       # "telnet" or "serial"
    host: str = ""
    port: int = 23
    serial_port: str = ""
    baudrate: int = 9600
    password: str = ""
    secret: str = ""

    def summary(self) -> str:
        if self.mode == "telnet":
            return f"{self.name} — telnet {self.host}:{self.port}"
        return f"{self.name} — serial {self.serial_port} @ {self.baudrate}"


def load_profiles() -> list[DeviceProfile]:
    path = _profiles_path()
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    profiles = []
    for entry in raw:
        try:
            profiles.append(DeviceProfile(**entry))
        except TypeError:
            continue  # skip entries with an unrecognized/outdated shape
    return profiles


def save_profiles(profiles: list[DeviceProfile]) -> None:
    config_dir = _config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    path = _profiles_path()
    path.write_text(json.dumps([asdict(p) for p in profiles], indent=2))
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def upsert_profile(profile: DeviceProfile) -> list[DeviceProfile]:
    """Add profile, or replace the existing one with the same name."""
    profiles = load_profiles()
    profiles = [p for p in profiles if p.name != profile.name]
    profiles.append(profile)
    save_profiles(profiles)
    return profiles


def delete_profile(name: str) -> list[DeviceProfile]:
    profiles = [p for p in load_profiles() if p.name != name]
    save_profiles(profiles)
    return profiles
