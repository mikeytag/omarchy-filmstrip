#!/usr/bin/env python3
"""Exercise the installed extension on the current Filmstrip workspace."""
import json
import os
from pathlib import Path
import subprocess
import time

cli=str(Path.home()/'.local/bin/omarchy-filmstrip')
def run(*args): return subprocess.check_output(args,text=True).strip()
def query(name): return json.loads(run('hyprctl',name,'-j'))
def action(*args): return run(cli,*args)
def sidebar(): return json.loads(run('/usr/share/omarchy/bin/omarchy-shell','filmstrip','status'))
def wait_for(check, description, seconds=4):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        if check(): return
        time.sleep(.1)
    raise AssertionError(description)

ws=query('activeworkspace')['id']
assert action('status')=='filmstrip', 'Run on a Filmstrip workspace'
initial=query('activewindow')['address']
def clients(): return [c for c in query('clients') if c['workspace']['id']==ws and not c['floating'] and not c['hidden']]
addresses=sorted(c['address'] for c in clients())
assert len(addresses)>=2
wait_for(lambda: len({tuple(c['size']) for c in clients()})==1,'Windows must share identical large dimensions')
size=clients()[0]['size']
seen=[]
for _ in addresses:
    before=query('activewindow')['address']
    action('next')
    expected=addresses[(addresses.index(before)+1)%len(addresses)]
    wait_for(lambda: query('activewindow')['address']==expected,'Next must focus the next thumbnail')
    seen.append(expected)
assert set(seen)==set(addresses),'Cycling must visit every window exactly once'
print('PASS: keyboard cycle reaches every window; geometry stays full size')
for address in addresses:
    # Exact path used by each sidebar card, including its workspace argument.
    action('focus',address.removeprefix('0x'),str(ws))
    wait_for(lambda: query('activewindow')['address']==address,'Click target did not receive focus')
assert all(c['size']==size for c in clients()),'Selecting thumbnails resized windows'
print('PASS: each thumbnail focuses its own full-size window')
wait_for(lambda: any(p['visible'] and len(p['windows'])==len(addresses) and all(w['ready'] and w['sourceWidth']>=size[0] for w in p['windows']) for p in sidebar()),'True window captures unavailable')
print('PASS: all miniatures contain compositor-captured full-resolution window content')
action('toggle')
wait_for(lambda: action('status')!='filmstrip' and not any(p['visible'] for p in sidebar()),'Rail must disappear when tiling returns')
action('toggle')
wait_for(lambda: action('status')=='filmstrip' and any(p['visible'] for p in sidebar()),'Filmstrip must return on the second toggle')
print('PASS: toggle hides and restores the sidebar')
# Lifecycle: an isolated temporary terminal, identified by its unique app-id.
p=subprocess.Popen(['foot','--app-id=filmstrip-test','--title=Filmstrip test','sh','-c','printf "Filmstrip lifecycle test\\n"; sleep 30'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
    wait_for(lambda: len(clients())==len(addresses)+1,'New window did not join the layout')
    wait_for(lambda: any(len(s['windows'])==len(addresses)+1 for s in sidebar()),'Sidebar did not add the new window')
    wait_for(lambda: len({tuple(c['size']) for c in clients()})==1,'Opening a new window changed the layout sizes')
finally:
    test=[c for c in clients() if c['class']=='filmstrip-test']
    for c in test:
        run('hyprctl','dispatch','hl.dsp.window.close({ window = "address:'+c['address']+'" })')
    try: p.wait(timeout=3)
    except subprocess.TimeoutExpired: p.terminate()
wait_for(lambda: len(clients())==len(addresses),'Test window did not close')
wait_for(lambda: any(len(s['windows'])==len(addresses) for s in sidebar()),'Closed window remained in the sidebar')
action('focus',initial,str(ws))
assert not run('hyprctl','configerrors')
print('PASS: new/closed windows update thumbnails; clean compositor configuration')
