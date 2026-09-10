#!/usr/bin/env python3
"""Real click regression, restricted to disposable test terminals."""
import json
import os
from pathlib import Path
import socket
import subprocess
import time

cli = str(Path.home() / '.local/bin/omarchy-filmstrip')
def run(*args):
    return subprocess.check_output(args, text=True).strip()
def query(name):
    return json.loads(run('hyprctl', name, '-j'))
def panel_status():
    return json.loads(run('/usr/share/omarchy/bin/omarchy-shell', 'filmstrip', 'status'))[0]

monitors = query('monitors')
assert len(monitors) == 1, 'Click test requires one monitor'
m = monitors[0]
width, height = round(m['width']/m['scale']), round(m['height']/m['scale'])
if m.get('transform', 0) % 2:
    width, height = height, width
ws = query('activeworkspace')['id']
items = sorted([c for c in query('clients') if c['workspace']['id'] == ws], key=lambda c: c['address'])
assert len(items) == 3 and all(c['class'] == 'filmstrip-click-test' for c in items), 'Use a workspace containing only three disposable test terminals'
assert run(cli, 'status') == 'filmstrip'
original = query('activewindow')['address']
cursor = query('cursorpos')
sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
sock.connect(os.environ['XDG_RUNTIME_DIR'] + '/hypr/' + os.environ['HYPRLAND_INSTANCE_SIGNATURE'] + '/.socket2.sock')
sock.setblocking(False)
def drain():
    data = b''
    while True:
        try:
            data += sock.recv(65536)
        except BlockingIOError:
            return data.decode().splitlines()
def click(x, y):
    run('/tmp/filmstrip-test-pointer', str(round(x)), str(round(y)), str(width), str(height), 'click')
    time.sleep(.12)
def assert_focus(address):
    assert query('activewindow')['address'] == address, 'Click selected a covered window'
    wrong = [line for line in drain() if line.startswith('activewindowv2>>') and line.split('>>')[1] != address.removeprefix('0x')]
    assert not wrong, 'Transient wrong-window focus: ' + str(wrong)
try:
    for c in items:
        run(cli, 'focus', c['address'], str(ws))
        time.sleep(.2)
        drain()
        x, y = c['at']; w, h = c['size']
        for dx, dy in [(.1,.1),(.8,.1),(.8,.8),(.2,.8),(.5,.5),(.95,.4),(.4,.95)]:
            click(x+w*dx, y+h*dy)
            assert_focus(c['address'])
    print('PASS: 21 actual main-window clicks; no wrong-window or transient focus')
    p = panel_status()
    assert p['visible'] and len(p['windows']) == 3
    for c in p['windows']:
        drain()
        click(width-p['width']+c['centerX'], height-p['height']+c['centerY'])
        time.sleep(.25)
        address = '0x' + c['address'].removeprefix('0x')
        assert_focus(address)
        click(width*.4, height*.5)
        assert_focus(address)
    print('PASS: actual thumbnail clicks select each window; subsequent main clicks stay there')
    for direction in ('next', 'prev'):
        before = query('activewindow')['address']
        run(cli, direction)
        time.sleep(.2)
        address = query('activewindow')['address']
        assert address != before
        drain()
        click(width*.4, height*.5)
        assert_focus(address)
    print('PASS: cycling followed by real clicks keeps the selected window')
finally:
    run(cli, 'focus', original, str(ws))
    run('/tmp/filmstrip-test-pointer', str(cursor['x']), str(cursor['y']), str(width), str(height))
    sock.close()
