# Cisco Catalyst 3560 GUI

A desktop GUI for managing a Catalyst 3560 switch over Telnet or a serial
console cable, built because the switch's own embedded web Device Manager
can't create VLANs — only Cisco Network Assistant could, and that's an
abandoned Java app from a decade+ ago.

This talks to the switch the same way you would by hand: it drives the IOS
CLI over Netmiko and screen-scrapes `show` command output. There is no API
on this thing — IOS 12.2(46)SE on the IP Base image doesn't have one.

## What it does

- **Dashboard** — live front-panel port map (24x FastEthernet + 2x Gigabit),
  color-coded by link/admin state, switch identity, fan/temp health
- **VLANs** — create, rename, delete
- **Ports** — description, admin up/down, access/trunk mode, VLAN
  assignment, speed/duplex
- **Interfaces / IP** — SVI (`interface Vlan X`) management, default gateway
- **Security / Users** — hostname, enable secret, console/VTY line
  passwords, local user accounts, HTTP server toggle
- **Terminal** — raw CLI passthrough for anything the other tabs don't cover

Auto-refreshes on a timer (default 20s, adjustable) and after every action,
so the GUI never drifts out of sync with what's actually on the switch.

## Requirements

- Python 3.10+
- A Catalyst 3560 (or close IOS relative) reachable over Telnet, or a
  USB-to-serial console cable

```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Running it

```
python3 main.py
```

You'll get a connection dialog on launch — pick Telnet or Serial, enter the
line password and enable secret, and it connects. Nothing is cached to
disk; credentials only live in memory for the session.

## Why Telnet and not SSH

This switch runs the non-crypto (`IPBASE`, not `IPBASEK9`) image, which
doesn't support SSH or HTTPS at all — `ssh` isn't even a recognized keyword
for `transport input`. If your switch has a crypto-capable image, Netmiko
supports SSH fine, it's just not wired up here since it wasn't usable
against the hardware this was built for.

## Architecture

- `core/device.py` — thin synchronous wrapper around Netmiko. All the
  blocking I/O lives here.
- `core/parsers.py` — regex/fixed-width-column parsing of `show` command
  output into plain dataclasses (`core/models.py`). No TextFSM/genie
  dependency — the output format of this specific platform/IOS version is
  simple enough that hand-written parsing is more predictable.
- `core/worker.py` — a `QObject` that owns the `SwitchDevice` and runs on a
  dedicated `QThread`, so Netmiko's blocking calls never freeze the UI.
- `gui/` — one file per tab, plus `main_window.py` wiring it all together.

**Threading rule that matters if you touch this code:** every call from the
GUI into the worker, and every result signal back, has to go through a real
`Signal` connected to a *bound method of a QObject* — never a `lambda` or a
direct method call. Qt can only auto-detect that a connection crosses
threads (and route it through the target thread's event loop) by inspecting
the receiving `QObject`'s thread affinity. A lambda has no such object to
inspect, so it silently runs on the *emitting* thread instead — which for
worker→GUI signals means GUI code executing on the network thread. This
showed up during development as
`QBasicTimer::start: Timers cannot be started from another thread` and
would freeze the UI on GUI→worker calls. See `gui/main_window.py` for the
pattern (`request_save_config` etc.).

## Known limitations

- No HTTPS/SSH (see above — hardware/image limitation, not a GUI limitation)
- No trunk allowed-VLAN diffing — setting trunk config always re-sends the
  full allowed-VLAN list rather than computing add/remove deltas
- No SNMP, no syslog, no config diffing/versioning — CLI-only, single
  switch at a time
