#!/usr/bin/env python3
"""Install Filmstrip into user-owned Omarchy configuration; never run with sudo."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

PLUGIN = 'mtaggart.filmstrip'
BEGIN = '-- BEGIN omarchy-filmstrip'
END = '-- END omarchy-filmstrip'


def jsonc(text):
    """Read JSON with comments/trailing commas without touching quoted strings."""
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*[\s\S]*?\*/|.', text, re.DOTALL)
    tokens = [t for t in tokens if not t.startswith(('//', '/*'))]
    for i, token in enumerate(tokens):
        if token == ',':
            following = next((t for t in tokens[i+1:] if not t.isspace()), '')
            if following in ('}', ']'):
                tokens[i] = ''
    value = json.loads(''.join(tokens))
    if not isinstance(value, dict):
        raise ValueError('Expected a JSON object')
    return value


def block(text, content):
    managed = BEGIN + '\n' + content.rstrip() + '\n' + END
    if BEGIN in text:
        if text.count(BEGIN) != 1 or text.count(END) != 1:
            raise ValueError('Malformed Filmstrip configuration block')
        return re.sub(re.escape(BEGIN) + r'[\s\S]*?' + re.escape(END), lambda _: managed, text)
    return text.rstrip() + '\n\n' + managed + '\n'


def build_plan(home, source, make_default=True, menu=True):
    """Validate all configuration before writing anything. Also used by tests."""
    config = home / '.config/hypr/hyprland.lua'
    if not config.is_file():
        raise ValueError('Requires an Omarchy installation with ~/.config/hypr/hyprland.lua (Lua configuration)')
    text = config.read_text()
    if 'require("default.hypr.omarchy")' not in text:
        raise ValueError('Unsupported Hyprland configuration: expected Omarchy Lua bootstrap')
    plan = {}
    for name in ('Service.qml', 'manifest.json'):
        plan[f'.config/omarchy/plugins/{PLUGIN}/{name}'] = (source / 'plugin' / name).read_text()
    plan['.local/bin/omarchy-filmstrip'] = (source / 'bin/omarchy-filmstrip').read_text()
    plan['.config/hypr/filmstrip.lua'] = ((source / 'hypr/filmstrip.lua').read_text() if make_default
                                       else '-- Filmstrip is selected per workspace with Super+L.\n')
    if 'require("hypr.filmstrip")' not in text:
        anchor = 'require("default.hypr.toggles")'
        if anchor not in text:
            raise ValueError('Cannot find saved-workspace layout loading point; install manually')
        text = text.replace(anchor, 'require("hypr.filmstrip")\n\n' + anchor, 1)
    plan['.config/hypr/hyprland.lua'] = text
    path = home / '.config/hypr/bindings.lua'
    bindings = path.read_text() if path.exists() else ''
    # Replace early local Filmstrip bindings, leaving unrelated shortcuts intact.
    bindings = '\n'.join(line for line in bindings.splitlines()
                         if not (line.startswith('o.bind(') and '/.local/bin/omarchy-filmstrip ' in line)) + '\n'
    lines = []
    for key, description, action in (
        ('SUPER + L', 'Toggle Filmstrip / previous layout', 'toggle'),
        ('ALT + TAB', 'Next Filmstrip window', 'next'),
        ('ALT + SHIFT + TAB', 'Previous Filmstrip window', 'prev'),
    ):
        lines += [f'hl.unbind("{key}")', f'o.bind("{key}", "{description}", "\\\"" .. os.getenv("HOME") .. "/.local/bin/omarchy-filmstrip\\\" {action}")']
    plan['.config/hypr/bindings.lua'] = block(bindings, '\n'.join(lines))
    shell_path = home / '.config/omarchy/shell.json'
    shell = jsonc(shell_path.read_text()) if shell_path.exists() else {}
    plugins = shell.setdefault('plugins', [])
    if not isinstance(plugins, list) or not all(isinstance(p, dict) for p in plugins):
        raise ValueError('Expected shell.json plugins to be an array of objects')
    existing = next((p for p in plugins if p.get('id') == PLUGIN), None)
    if existing is None:
        plugins.append({'id': PLUGIN, 'showHeader': False, 'showFooter': False, 'backgroundOpacity': 0})
    if 'disabledPlugins' in shell:
        shell['disabledPlugins'] = [p for p in shell['disabledPlugins'] if p != PLUGIN]
    plan['.config/omarchy/shell.json'] = json.dumps(shell, ensure_ascii=False, indent=2) + '\n'
    if menu:
        path = home / '.config/omarchy/extensions/omarchy-menu.jsonc'
        entries = jsonc(path.read_text()) if path.exists() else {}
        entries.setdefault('style.layout', {'icon': '󱂬', 'label': 'Window Layout', 'aliases': ['layout', 'filmstrip']})
        for name, label in [('filmstrip', 'Filmstrip'), ('dwindle', 'Tiling'), ('scrolling', 'Scrolling'), ('master', 'Master')]:
            key = 'style.layout.' + name
            item = {'label': label, 'action': f'"$HOME/.local/bin/omarchy-filmstrip" layout {name}',
                    'checked': f'[[ $("$HOME/.local/bin/omarchy-filmstrip" status) == {name} ]]'}
            if key in entries and entries[key] != item:
                raise ValueError(f'Menu entry {key} already exists; use --no-menu to preserve it')
            entries[key] = item
        plan['.config/omarchy/extensions/omarchy-menu.jsonc'] = json.dumps(entries, ensure_ascii=False, indent=2) + '\n'
    for path in (home / '.local/state/omarchy/workspace-layouts').glob('*.lua'):
        old = path.read_text()
        new = re.sub(r'^filmstrip_pointer\([^\n]*\)\n?', '', old, flags=re.MULTILINE).replace('lua:filmstrip', 'monocle')
        if new != old:
            plan[str(path.relative_to(home))] = new
    return plan


def digest(data):
    return hashlib.sha256(data).hexdigest()


def apply_plan(home, plan):
    changes = {rel: text.encode() for rel, text in plan.items()
               if not (home / rel).exists() or (home / rel).read_bytes() != text.encode()}
    if not changes:
        return None
    backup = home / '.local/state/omarchy/filmstrip' / ('install-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    backup.mkdir(parents=True)
    manifest = {}
    for rel, data in changes.items():
        path = home / rel
        manifest[rel] = {'existed': path.exists(), 'installed_sha256': digest(data)}
        if path.exists():
            dest = backup / 'files' / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
    (backup / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    try:
        for rel, data in changes.items():
            path = home / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            if rel == '.local/bin/omarchy-filmstrip':
                path.chmod(0o755)
    except OSError:
        # Restore the complete pre-install snapshot after a partial write.
        for rel, entry in manifest.items():
            path = home / rel
            if entry['existed']:
                shutil.copy2(backup / 'files' / rel, path)
            else:
                path.unlink(missing_ok=True)
        raise
    return backup


def restore(home, backup):
    manifest = json.loads((backup / 'manifest.json').read_text())
    for rel, entry in manifest.items():
        if Path(rel).is_absolute() or '..' in Path(rel).parts:
            raise ValueError('Invalid backup path')
        path = home / rel
        if not path.exists() or digest(path.read_bytes()) != entry['installed_sha256']:
            raise ValueError(f'{rel} changed since installation. Restore it manually from {backup / "files"}; no files were changed.')
    for rel, entry in manifest.items():
        path = home / rel
        if entry['existed']:
            shutil.copy2(backup / 'files' / rel, path)
        else:
            path.unlink()


def reload_desktop():
    subprocess.run(['hyprctl', 'reload'], check=True)
    result = subprocess.check_output(['hyprctl', 'configerrors'], text=True).strip()
    if result:
        raise ValueError('Hyprland configuration errors:\n' + result)
    subprocess.run(['omarchy', 'restart', 'shell'], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--no-default', action='store_true', help='keep the existing default layout; enable Filmstrip per workspace')
    parser.add_argument('--no-menu', action='store_true', help='leave menu extensions untouched')
    parser.add_argument('--dry-run', action='store_true', help='validate and list files without writing or reloading')
    parser.add_argument('--no-reload', action='store_true', help='write files without reloading the desktop')
    parser.add_argument('--restore', type=Path, metavar='BACKUP', help='restore a backup if installed files have not subsequently changed')
    args = parser.parse_args()
    home = Path.home()
    if args.restore:
        if args.dry_run:
            parser.error('--restore and --dry-run cannot be combined')
        restore(home, args.restore.expanduser())
        print('Restored backup:', args.restore)
    else:
        plan = build_plan(home, Path(__file__).resolve().parent, not args.no_default, not args.no_menu)
        if args.dry_run:
            print('\n'.join(str(home / rel) for rel in plan))
            return
        backup = apply_plan(home, plan)
        print('Backup:', backup if backup else 'No file changes needed')
    if not args.no_reload:
        reload_desktop()
    print('Filmstrip configuration applied.' if not args.restore else 'Previous configuration restored.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        raise SystemExit(f'Filmstrip installer: {error}')
