# CLAUDE.md

Notes for whichever Claude session touches this repo next.

## What this is

A PySide6 GUI that manages a Cisco Catalyst 3560 (IOS 12.2(46)SE, IP Base
image) over Telnet or a serial console cable, via Netmiko. See README.md
for the user-facing picture. This file is about things that aren't obvious
from reading the code.

## The one rule that actually matters here

**Every GUI→worker call and every worker→GUI result must go through a real
`Signal` connected to a bound method of a `QObject`.** Never a `lambda`,
never a direct method call like `self.worker.some_method()`.

Why: `SwitchDevice` does blocking I/O, so it only ever runs on the
background thread owned by `DeviceWorker` (see `core/worker.py`,
`gui/main_window.py`). Qt's `AutoConnection` only knows to marshal a call
across threads when it can inspect the *receiving QObject's* thread
affinity — which it can do for a bound method (`obj.method`, where
`obj.__self__` is a QObject) but **not** for a lambda or plain function,
which have no such object to inspect. Connect a signal from the worker
thread to a lambda that touches GUI state, and the lambda runs directly on
the worker thread instead of being queued to the main thread.

This bit me twice while building this:
1. Two lambdas in `main_window.py` calling `QStatusBar.showMessage(...,
   timeout)` from worker signals produced
   `QBasicTimer::start: Timers cannot be started from another thread` and
   aborted the process. Fixed by replacing them with real bound methods
   (`_on_action_done`, `_on_config_saved`).
2. The "Save to Startup-Config" toolbar action called
   `self.worker.save_config()` directly — a plain Python call, not a signal
   emit — which ran the blocking Netmiko save **on the GUI thread**,
   freezing the window for the duration. Fixed with a bridging
   `request_save_config = Signal()` connected to `worker.save_config`.

If you add a new action, follow the existing pattern: a `Signal` on the tab
widget (e.g. `VlanTab.create_vlan_requested`), connected in
`MainWindow._wire_tab_signals` to a `@Slot`-decorated method on
`DeviceWorker`. Never call `self.worker.*` or `self.device.*` directly from
GUI code outside that wiring.

## Layout

- `core/models.py` — plain dataclasses, no logic.
- `core/parsers.py` — turns raw CLI text into the dataclasses above. Pure
  functions, no I/O, so they're cheap to unit-test against captured output.
- `core/device.py` — `SwitchDevice`, a synchronous Netmiko wrapper. Blocking
  by design; only ever called from the worker thread.
- `core/worker.py` — `DeviceWorker(QObject)`, lives on a `QThread`, owns the
  `SwitchDevice`, exposes every action as a `@Slot` and every result as a
  `Signal`.
- `core/profiles.py` — load/save of saved device connections to
  `~/.config/cisco3560-gui/devices.json` (`$XDG_CONFIG_HOME` if set). Plain
  functions (`load_profiles`, `save_profiles`, `upsert_profile`,
  `delete_profile`), no Qt dependency, synchronous — this is small/local
  disk I/O, not worth routing through the worker thread. Includes
  credentials in plaintext by deliberate user choice; file gets chmod'd
  `0600` after every write. Never write a test/profile file into the real
  `$HOME/.config` — point `$XDG_CONFIG_HOME` at a scratch dir first.
- `gui/*_tab.py` — one file per tab. Each tab only knows about its own
  `Signal`s (requests) and `update_*()` methods (results) — it never talks
  to `core/` directly.
- `gui/connection_dialog.py` — the one exception to "GUI never talks to
  core/ directly": it calls `core/profiles.py` synchronously (see above).
- `gui/main_window.py` — the only file that wires tabs to the worker.

## Interface naming gotcha

IOS uses short names (`Fa0/1`, `Gi0/1`) in `show interfaces status` /
`show vlan brief`, but long names (`FastEthernet0/1`, `GigabitEthernet0/1`)
in `show running-config` interface blocks. `parsers.expand_interface_name`
/ `shorten_interface_name` convert between them. `PortInfo.name` is always
short form; `device.py` expands it before sending config commands.

## `running_config` is fetched once per refresh, not per getter

`get_ports`, `get_svis`, `get_local_users`, `get_line_configs`, and
`get_default_gateway` all need `show running-config` output, but each
accepts an optional `running_config` param instead of fetching it
themselves. `DeviceWorker._refresh_all_inner` fetches it once and passes it
through. Originally each getter fetched it independently — six redundant
`show running-config` round trips per refresh cycle, ~4s of dead time per
action. If you add a new getter that needs running-config, follow the same
`running_config: str | None = None` pattern rather than calling
`self.get_running_config()` again inside it.

## Testing against real hardware

There's no mock/simulator — this was built and tested entirely against a
real WS-C3560-24TS reachable over Telnet on the LAN. If you're iterating on
this code, ask the user for the switch's current IP and Telnet/enable
credentials rather than assuming — don't hardcode credentials into test
scripts you leave lying around, and definitely don't commit them.

Useful pattern for headless verification (no real display needed):

```
QT_QPA_PLATFORM=offscreen python3 your_test_script.py
```

`QWidget.grab()` renders correctly even under the offscreen platform, so
`window.grab().save("out.png")` is a reliable way to visually check GUI
state without a real compositor.

**Don't gate assertions on fixed-time `QTimer.singleShot` waits.** A full
refresh cycle (9 sequential `show` commands, several seconds over Telnet)
takes a few seconds, and a single GUI action triggers a full refresh
afterward. Wait on the actual completion signal (`vlans_updated`,
`terminal_output`, etc.) instead of guessing a delay — short fixed waits
produced false "it's broken" readings twice during development when the
real issue was just that the assertion fired before the refresh finished.

## Parser changes

If you touch `core/parsers.py`, capture real output first
(`send_command("show ...")` over an actual Netmiko session) and test the
parser against that — don't guess the format from memory or docs. The
column-based table parser (`parse_table`/`_columns`/`_split_row`) assumes
fixed-width Cisco tables where only the last column can contain values
wider than the header; that held for every command used here but isn't a
universal guarantee across IOS versions.
