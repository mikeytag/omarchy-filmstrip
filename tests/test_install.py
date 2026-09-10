"""Installer integration tests against disposable home directories."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('installer', SOURCE / 'install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.put('.config/hypr/hyprland.lua', 'require("default.hypr.omarchy")\nrequire("hypr.bindings")\nrequire("default.hypr.toggles")\n')
        self.put('.config/hypr/bindings.lua', 'o.bind("SHIFT + PRINT", "Screenshot", "custom-screenshot")\n')

    def put(self, rel, text):
        path = self.home / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def snapshot(self):
        return {str(p.relative_to(self.home)): p.read_bytes() for p in self.home.rglob('*')
                if p.is_file() and '/filmstrip/install-' not in str(p)}

    def plan(self, **kwargs):
        return installer.build_plan(self.home, SOURCE, **kwargs)

    def test_fresh_install_and_rollback(self):
        original = self.snapshot()
        backup = installer.apply_plan(self.home, self.plan())
        bindings = (self.home / '.config/hypr/bindings.lua').read_text()
        self.assertIn('custom-screenshot', bindings)
        self.assertIn('hl.unbind("ALT + TAB")', bindings)
        self.assertIn('omarchy-filmstrip\\\" toggle', bindings)
        self.assertTrue((self.home / '.local/bin/omarchy-filmstrip').stat().st_mode & 0o111)
        self.assertEqual(json.loads((self.home / '.config/omarchy/shell.json').read_text())['plugins'][0]['id'], installer.PLUGIN)
        installer.restore(self.home, backup)
        self.assertEqual(original, self.snapshot())

    def test_idempotent_install(self):
        installer.apply_plan(self.home, self.plan())
        before = self.snapshot()
        self.assertIsNone(installer.apply_plan(self.home, self.plan()))
        self.assertEqual(before, self.snapshot())

    def test_plan_does_not_write(self):
        before = self.snapshot()
        self.plan()
        self.assertEqual(before, self.snapshot())

    def test_existing_settings_and_jsonc(self):
        self.put('.config/omarchy/extensions/omarchy-menu.jsonc', '{ // menu\n "custom": {"action": "echo https://example.com/a,}",}, /* note */ }')
        self.put('.config/omarchy/shell.json', json.dumps({'plugins': [{'id': 'other.plugin'}, {'id': installer.PLUGIN, 'showHeader': True, 'backgroundOpacity': .4}], 'idle': {'lock': 600}, 'disabledPlugins': [installer.PLUGIN, 'other.disabled']}))
        plan = self.plan()
        menu = json.loads(plan['.config/omarchy/extensions/omarchy-menu.jsonc'])
        shell = json.loads(plan['.config/omarchy/shell.json'])
        self.assertEqual(menu['custom']['action'], 'echo https://example.com/a,}')
        self.assertEqual(shell['idle']['lock'], 600)
        self.assertEqual(shell['plugins'][1]['backgroundOpacity'], .4)
        self.assertEqual(shell['disabledPlugins'], ['other.disabled'])

    def test_conflicting_menu_fails_before_write(self):
        self.put('.config/omarchy/extensions/omarchy-menu.jsonc', '{"style.layout.filmstrip": {"action": "my-command"}}')
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.plan()
        self.assertEqual(before, self.snapshot())
        self.assertNotIn('.config/omarchy/extensions/omarchy-menu.jsonc', self.plan(menu=False))

    def test_no_default_and_saved_layouts(self):
        self.put('.local/state/omarchy/workspace-layouts/2.lua', 'hl.workspace_rule({workspace="2",layout="master"})\n')
        plan = self.plan(make_default=False)
        self.assertNotIn('hl.config', plan['.config/hypr/filmstrip.lua'])
        self.assertNotIn('.local/state/omarchy/workspace-layouts/2.lua', plan)

    def test_legacy_layout_migration(self):
        self.put('.local/state/omarchy/workspace-layouts/2.lua', 'filmstrip_pointer("2", true)\nhl.workspace_rule({workspace="2",layout="lua:filmstrip"})\n')
        text = self.plan()['.local/state/omarchy/workspace-layouts/2.lua']
        self.assertNotIn('filmstrip_pointer', text)
        self.assertNotIn('lua:filmstrip', text)
        self.assertIn('monocle', text)

    def test_refuse_rollback_over_later_edits(self):
        backup = installer.apply_plan(self.home, self.plan())
        self.put('.config/hypr/bindings.lua', '-- later user edit\n')
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'changed since installation'):
            installer.restore(self.home, backup)
        self.assertEqual(before, self.snapshot())

    def test_unsupported_config_does_not_write(self):
        self.put('.config/hypr/hyprland.lua', '-- custom non-Omarchy config\n')
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            self.plan()
        self.assertEqual(before, self.snapshot())


if __name__ == '__main__':
    unittest.main()
