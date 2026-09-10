#!/usr/bin/env python3
"""Regression: pointer movement must not switch overlapping Filmstrip windows."""
import json
import os
from pathlib import Path
import socket
import subprocess
import time

cli=str(Path.home()/'.local/bin/omarchy-filmstrip')
def run(*args): return subprocess.check_output(args,text=True).strip()
def query(name): return json.loads(run('hyprctl',name,'-j'))
def move(x,y): run('/tmp/filmstrip-test-pointer',str(x),str(y),str(extent_width),str(extent_height))

monitors=query('monitors')
assert len(monitors)==1, 'Pointer test currently requires a single monitor'
monitor=monitors[0]
extent_width=round(monitor['width']/monitor['scale'])
extent_height=round(monitor['height']/monitor['scale'])
if monitor.get('transform',0) % 2: extent_width,extent_height=extent_height,extent_width
assert run(cli,'status')=='filmstrip'
ws=query('activeworkspace')['id']
original_cursor=query('cursorpos')
original_window=query('activewindow')['address']
items=sorted([c for c in query('clients') if c['workspace']['id']==ws and not c['floating'] and not c['hidden']],key=lambda c:c['address'])
assert len(items)>1
sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
sock.connect(os.environ['XDG_RUNTIME_DIR']+'/hypr/'+os.environ['HYPRLAND_INSTANCE_SIGNATURE']+'/.socket2.sock')
sock.setblocking(False)
def drain():
    result=b''
    while True:
        try: result+=sock.recv(65536)
        except BlockingIOError: break
    return result
try:
    for c in items:
        run(cli,'focus',c['address'],str(ws))
        time.sleep(.15)
        drain()
        x,y=c['at']; width,height=c['size']
        events=b''
        for dx,dy in [(0.1,.1),(.8,.1),(.8,.8),(.2,.8),(.5,.5),(.95,.4),(.4,.95)]:
            move(round(x+width*dx),round(y+height*dy))
            time.sleep(.04)
            events+=drain()
            assert query('activewindow')['address']==c['address'],'Moving the mouse changed the selected Filmstrip window'
        changes=[line for line in events.decode().splitlines() if line.startswith('activewindowv2>>') and line.split('>>')[1] != c['address'].removeprefix('0x')]
        assert not changes, 'Transient focus oscillation: '+str(changes)
    print('PASS: pointer sweeps over every selected window caused no focus changes or transient oscillation')
    run(cli,'toggle')
    assert run(cli,'status')!='filmstrip'
    time.sleep(.6)  # Wait for rail removal and layout animations before hit-testing.
    tiled=[c for c in query('clients') if c['workspace']['id']==ws and not c['floating']]
    for c in tiled:
        x,y=c['at']; w,h=c['size']
        move(round(x+w/2),round(y+h/2))
        time.sleep(.1)
        assert query('activewindow')['address']==c['address'],'Normal tiling lost hover-to-focus'
    print('PASS: normal hover-to-focus returns when Filmstrip is disabled')
finally:
    if run(cli,'status')!='filmstrip': run(cli,'enable')
    run(cli,'focus',original_window,str(ws))
    move(original_cursor['x'],original_cursor['y'])
    sock.close()
