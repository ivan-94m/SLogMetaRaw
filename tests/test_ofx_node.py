# SPDX-License-Identifier: GPL-3.0-or-later
"""The node's behaviour in the test host: unlocking without metadata, bounded waits on the
reader, formats that never start Python, and the version button."""
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tests'))
from plugin_build import BUNDLE_BINARY, test_bin  # noqa: E402

TRUSTED = 'https://github.com/ivan-94m/SLogMetaRaw/releases/download/v9.9.9/SLogMetaRaw-9.9.9.dmg'


def release():
    with open(os.path.join(ROOT, 'slogmetaraw', '__init__.py'), encoding='utf-8') as fh:
        return fh.read().split("__version__ = '")[1].split("'")[0]


class Node(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exe = test_bin('host_test')
        if not cls.exe or not os.path.exists(BUNDLE_BINARY):
            raise unittest.SkipTest('plugin o host di test non compilabili qui')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / 'home'
        self.support = self.home / 'Library/Application Support/SLogMetaRaw'
        self.support.mkdir(parents=True)
        self.sentinel = Path(self.tmp.name) / 'launched'

    def tearDown(self):
        self.tmp.cleanup()

    def fake_library(self, body):
        """A slogmetaraw package whose __main__ is `body`; every launch appends to the sentinel."""
        package = Path(self.tmp.name) / 'lib' / 'slogmetaraw'
        package.mkdir(parents=True)
        (package / '__init__.py').write_text('', encoding='utf-8')
        (package / '__main__.py').write_text(
            'import sys, time, json\n'
            'open(%r, "a").write(" ".join(sys.argv[1:]) + "\\n")\n' % str(self.sentinel) + body,
            encoding='utf-8')
        (self.support / 'lib_path').write_text(str(package.parent) + '\n', encoding='utf-8')

    def clip(self, name):
        path = Path(self.tmp.name) / name
        path.write_bytes(b'not a real clip')
        return str(path)

    def run_host(self, *args, env=None):
        child_env = dict(os.environ, HOME=str(self.home), SLOGMETARAW_TEST_NO_RESOLVE='1',
                         SLOGMETARAW_NO_UPDATE_CHECK='1', SLOGMETARAW_TEST_NO_OPEN='1')
        child_env.update(env or {})
        start = time.monotonic()
        run = subprocess.run([self.exe, BUNDLE_BINARY] + list(args), capture_output=True, text=True,
                             env=child_env, timeout=30)
        self.elapsed = time.monotonic() - start
        self.stderr = run.stderr
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        return dict(line.split('=', 1) for line in run.stdout.splitlines() if '=' in line)

    def launches(self):
        return self.sentinel.read_text(encoding='utf-8').splitlines() if self.sentinel.exists() else []

    # ---- unlock without metadata

    def test_without_metadata_the_controls_stay_locked_and_say_how_to_unlock(self):
        v = self.run_host(self.clip('a.mov'))
        self.assertEqual(v['enabled:exposure'], '0')
        self.assertEqual(v['secret:shotEI'], '1')
        self.assertIn('Sblocca', v['camera'])
        self.assertEqual(v['identity'], '1')

    def test_unlocking_starts_neutral_on_the_typed_references(self):
        v = self.run_host(self.clip('a.mov'), '--set', 'nodeInput=2', '--set', 'unlockNoMeta=1',
                          '--change', 'unlockNoMeta')
        self.assertEqual(v['enabled:exposure'], '1')
        self.assertEqual((v['secret:shotEI'], v['enabled:shotEI']), ('0', '1'))
        self.assertEqual(v['refSource'], '2')
        self.assertEqual(v['identity'], '1', 'appena sbloccato il nodo deve essere neutro')
        self.assertIn('sbloccato', v['camera'])

    def test_unlocking_with_an_unknown_input_keeps_the_node_neutral(self):
        """S-Log3 read as another curve would make Exposure and White Balance non-linear."""
        v = self.run_host(self.clip('a.mov'), '--set', 'unlockNoMeta=1', '--change', 'unlockNoMeta')
        self.assertEqual(v['enabled:exposure'], '0')
        self.assertIn('Ingresso non noto', v['camera'])
        self.assertEqual(v['identity'], '1')

    def test_a_new_reference_changes_the_numbers_not_the_picture(self):
        v = self.run_host(self.clip('a.mov'), '--set', 'nodeInput=2', '--set', 'unlockNoMeta=1',
                          '--change', 'unlockNoMeta', '--change', 'exposure=1600', '--change', 'shotEI=3200')
        self.assertEqual(float(v['exposure']), 6400.0)
        v = self.run_host(self.clip('a.mov'), '--set', 'nodeInput=2', '--set', 'unlockNoMeta=1',
                          '--change', 'unlockNoMeta', '--change', 'shotTemp=3200')
        self.assertEqual(float(v['colorTemp']), 3200.0, 'As shot segue il riferimento')

    # ---- the reader

    def test_formats_that_carry_no_sony_metadata_never_start_python(self):
        self.fake_library('')
        for name in ('a.mov', 'b.MOV', 'c.braw', 'd.r3d'):
            v = self.run_host(self.clip(name), '--begin-edit')
            self.assertIn('non Sony', v['status'])
        self.assertEqual(self.launches(), [])

    def test_creating_the_node_never_starts_the_reader(self):
        """Opening a project builds every node: only the cache is read there."""
        self.fake_library('')
        self.run_host(self.clip('a.MP4'), '--no-reload')
        self.assertEqual(self.launches(), [])

    def test_a_slow_reader_does_not_freeze_the_panel(self):
        self.fake_library('time.sleep(4)\n')
        v = self.run_host(self.clip('a.MP4'), '--no-reload', '--begin-edit')
        self.assertLess(self.elapsed, 1.5)
        self.assertIn('in corso', v['camera'])
        self.assertEqual(len(self.launches()), 1)
        self.assertIn('--max-samples', self.launches()[0])

    def test_reload_waits_two_seconds_at_most(self):
        self.fake_library('time.sleep(5)\n')
        self.run_host(self.clip('a.MP4'))
        self.assertLess(self.elapsed, 3.0)

    # ---- the version button

    def update_reader(self, latest, url, lib=None):
        self.fake_library(
            'if sys.argv[1] == "--update-check":\n'
            '    print(json.dumps({"ok": 1, "newer": 1, "latest": %r, "dmg_url": %r, "lib_version": %r,'
            ' "title": "S-Log MetaRaw %s", "error": ""}))\n' % (latest, url, lib or release(), latest))

    def test_the_version_is_the_first_row_and_reads_the_release(self):
        v = self.run_host('--no-reload')
        self.assertEqual(v['label:version'], 'v' + release())
        self.assertEqual(self.launches(), [], 'con opt-out nessun controllo automatico')

    def test_a_newer_release_lights_the_button(self):
        self.update_reader('9.9.9', TRUSTED)
        v = self.run_host('--no-reload', '--change', 'version')
        self.assertIn('\U0001F7E2', v['label:version'])
        self.assertIn('9.9.9', v['label:version'])
        self.assertTrue(any(l.startswith('--update-check') and '--force' in l for l in self.launches()))

    def test_an_untrusted_installer_is_never_offered(self):
        for url in ('https://github.com/someone/SLogMetaRaw/releases/download/v9/x.dmg',
                    'http://github.com/ivan-94m/SLogMetaRaw/releases/download/v9/x.dmg',
                    'https://github.com/ivan-94m/SLogMetaRaw/releases/download/../x.dmg',
                    'https://github.com/ivan-94m/SLogMetaRaw/releases/download/v9/x.dmg?a=1'):
            self.tearDown()
            self.setUp()
            self.update_reader('9.9.9', url)
            v = self.run_host('--no-reload', '--change', 'version')
            self.assertNotIn('\U0001F7E2', v['label:version'], url)

    def test_the_second_click_hands_the_installer_to_the_browser(self):
        self.update_reader('9.9.9', TRUSTED)
        v = self.run_host('--no-reload', '--change', 'version', '--change', 'version')
        self.assertIn('[open] ' + TRUSTED, self.stderr)
        self.assertIn('nel browser', v['label:version'])

    def test_an_installed_but_not_loaded_update_asks_for_a_restart(self):
        self.update_reader('9.9.9', TRUSTED, lib='9.9.9')
        v = self.run_host('--no-reload', '--change', 'version')
        self.assertIn('riavvia Resolve', v['label:version'])


if __name__ == '__main__':
    unittest.main()
