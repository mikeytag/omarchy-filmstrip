# Testing Filmstrip

## Installer

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

These tests use temporary home directories. They cover a fresh install, repeat
installation, rollback, preservation of unrelated settings, JSONC parsing, menu
conflicts, unsupported configuration, legacy layout migration, and refusing to
overwrite later edits during rollback. They do not contact Hyprland or GitHub.

## Live desktop tests

These tests require an installed Filmstrip and a live Wayland session. They
visibly switch windows and temporarily toggle layouts. Finish any sensitive
interaction before running them. The pointer/click tests currently support one
monitor only; the pointer test expects normal tiling to use focus-follows-mouse.

With at least two tiled windows in the current Filmstrip workspace:

```sh
python3 tests/live.py
```

This exercises window cycling, preview selection commands, capture availability,
layout toggling, and opening/closing a temporary Foot terminal. Foot is a test
dependency, not a runtime requirement for Filmstrip.

### Build the real pointer helper

Cursor-warp dispatchers alone do not exercise actual pointer hit-testing. The
test helper uses the Wayland virtual-pointer protocol for real motion and clicks.
It requires a C compiler, Wayland development headers/library, and `wayland-scanner`.

```sh
curl -fsSL https://raw.githubusercontent.com/swaywm/wlr-protocols/master/unstable/wlr-virtual-pointer-unstable-v1.xml -o /tmp/filmstrip-virtual-pointer.xml
wayland-scanner client-header /tmp/filmstrip-virtual-pointer.xml /tmp/filmstrip-virtual-pointer.h
wayland-scanner private-code /tmp/filmstrip-virtual-pointer.xml /tmp/filmstrip-virtual-pointer.c
cc -I/tmp tests/virtual-pointer.c /tmp/filmstrip-virtual-pointer.c -lwayland-client -o /tmp/filmstrip-test-pointer
python3 tests/pointer.py
```

This sweeps the main area while every window is selected, checks compositor focus
events for transient switches, then verifies normal tiling hover-to-focus returns.

### Real clicks

Switch to an otherwise empty workspace, enable Filmstrip, and open exactly three
disposable Foot windows:

```sh
~/.local/bin/omarchy-filmstrip enable
for i in 1 2 3; do
  foot --app-id=filmstrip-click-test --title="Filmstrip test $i" sh -c 'printf "Safe test window\n"; sleep 900' &
done
python3 tests/clicks.py
```

Run the test from another terminal/session without adding a fourth window to the
test workspace. Keep that workspace active and leave the pointer alone until the
test finishes. The test refuses to run unless the workspace contains only three
`filmstrip-click-test` windows. It clicks across each main window, clicks actual
thumbnails using their reported coordinates, and checks cycling followed by
clicks. Close the disposable windows afterward.

Do not substitute real application windows for these terminals: a regression
could deliver a click to a different app than intended.

## Reported validation

The pre-publication desktop build passed main-window clicks, actual thumbnail
clicks, pointer sweeps, window cycling, capture, layout toggling, window lifecycle,
and single-window expansion on Hyprland 0.56.2 / Quickshell 0.3.1 with one scaled
monitor. Installer tests run independently of that desktop session.
