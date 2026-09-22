# SPDX-License-Identifier: GPL-3.0-or-later
"""Load the built plugin in a miniature OpenFX host and run the actions Resolve runs.

This is the check that would have caught the two crashes we hit in DaVinci Resolve:
a duplicate parameter name, and a set of claimed names shared between the two
describeInContext calls (which left the second context with no parameters).
"""
import os
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OFX = os.path.join(ROOT, 'ofx', 'SLogMetaRaw')
SDK = os.path.join(OFX, '.ofxsdk')
BINARY = os.path.join(OFX, 'SLogMetaRaw.ofx.bundle', 'Contents', 'MacOS', 'SLogMetaRaw.ofx')


class OfxHost(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('clang++'):
            raise unittest.SkipTest('clang++ non disponibile')
        if not os.path.exists(BINARY):
            raise unittest.SkipTest('plugin non compilato (make in ofx/SLogMetaRaw)')
        if not os.path.isdir(SDK):
            raise unittest.SkipTest('SDK OpenFX non trovato')
        cls.tmp = tempfile.mkdtemp()
        cls.exe = os.path.join(cls.tmp, 'host_test')
        subprocess.run(['clang++', '-std=c++17', '-O1', '-o', cls.exe,
                        os.path.join(ROOT, 'tests', 'host_test.cpp'),
                        '-I', os.path.join(SDK, 'OpenFX-1.4', 'include'),
                        '-I', os.path.join(SDK, 'Support', 'include')], check=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(getattr(cls, 'tmp', ''), ignore_errors=True)

    def run_host(self, clip=None, env=None):
        child_env = dict(env if env is not None else os.environ)
        # The plugin's "Rileggi metadata" now also writes into Resolve: tests must
        # never touch a real Resolve, so the child skips the connection.
        child_env['SLOGMETARAW_TEST_NO_RESOLVE'] = '1'
        run = subprocess.run([self.exe, BINARY] + ([clip] if clip else []), capture_output=True, text=True,
                             env=child_env, timeout=20)
        report = run.stdout + run.stderr
        self.assertEqual(run.returncode, 0, 'il plugin non supera il caricamento:\n' + report)
        self.assertIn('OK', run.stdout, report)
        self.assertNotIn('DUPLICATO', report)
        return dict(line.split('=', 1) for line in run.stdout.splitlines() if '=' in line)

    def test_load_describe_and_both_contexts(self):
        self.run_host()

    def test_instance_without_a_clip_stays_neutral(self):
        """No source path (a compound clip, for instance): the node must still build."""
        values = self.run_host()
        self.assertEqual(values['metaValid'], '0')
        self.assertIn('percorso', values['status'])

    def test_data_level_starts_on_automatico_and_corrects_nothing(self):
        """With no metadata the data level stage has nothing to go on, and a node that
        corrects a clip it knows nothing about would be worse than one that does not."""
        values = self.run_host()
        self.assertEqual(values['dataLevel'], '0')        # Automatico
        self.assertEqual(values['levelRequired'], '-1')   # nothing read yet
        self.assertEqual(values['levelHost'], '-1')       # Resolve not asked yet
        self.assertIn('non nota', values['levelInfo'])

    def test_instance_sets_itself_to_the_clip(self):
        clip = os.path.join(ROOT, 'samples', 'Sony FX30', 'F002C005_260717TL.MP4')
        if not os.path.exists(clip):
            raise unittest.SkipTest('clip di esempio non presente')
        subprocess.run([sys.executable, '-m', 'slogmetaraw', '--cache', clip],
                       cwd=ROOT, check=True, capture_output=True)
        values = self.run_host(clip)
        self.assertEqual(values['camera'], 'Sony ILME-FX30 (FX30)')
        self.assertEqual(values['metaValid'], '1')
        self.assertEqual(float(values['colorTemp']), 4000)
        self.assertEqual(float(values['exposure']), 4000)

    def test_missing_cache_launches_isolated_resolve_python(self):
        """The OFX fallback must import its library even when PYTHONPATH is ignored."""
        bundled = '/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/'
        if not any(os.access(bundled + suffix, os.X_OK) for suffix in (
                'Applications/ResolvePython', 'Resources/ResolvePython/ResolvePython')):
            self.skipTest('ResolvePython bundled non disponibile')
        with tempfile.TemporaryDirectory() as directory:
            user_directory = Path(directory) / 'user'
            support = user_directory / 'Library/Application Support/SLogMetaRaw'
            support.mkdir(parents=True)
            library = Path(directory) / "libreria d'Ivan & è"
            package = library / 'slogmetaraw'
            package.mkdir(parents=True)
            (package / '__init__.py').write_text('', encoding='utf-8')
            clip = Path(directory) / "clip d'Ivan è.MP4"
            clip.write_bytes(b'fixture: only the subprocess bootstrap is under test')
            # The fake reader isolates process launching from Sony parsing. It must
            # receive the exact clip path and create the record the real plugin reads;
            # in --to-resolve mode (the reload button) it also prints the JSON result.
            record = {'supported': 1, 'camera_name': 'Bootstrap test camera',
                      'shot_temp': 4300, 'shot_tint': 0, 'shot_ei': 1250}
            reader = (
                'import json, os, sys, unicodedata\n'
                'from pathlib import Path\n'
                'assert sys.argv[1] in ("--cache", "--to-resolve"), sys.argv\n'
                'assert sys.argv[2] == ' + repr(str(clip)) + '\n'
                'value = 0xcbf29ce484222325\n'
                'for byte in unicodedata.normalize("NFC", sys.argv[2]).encode("utf-8"):\n'
                '    value = ((value ^ byte) * 0x100000001b3) & 0xffffffffffffffff\n'
                'cache = Path(os.environ["HOME"]) / "Library/Application Support/SLogMetaRaw/cache"\n'
                'cache.mkdir(parents=True, exist_ok=True)\n'
                '(cache / ("%016x.json" % value)).write_text(' + repr(json.dumps(record)) + ', encoding="utf-8")\n'
                'if sys.argv[1] == "--to-resolve":\n'
                '    print(json.dumps({"ok": 1, "written": 34, "failed": 0, "clips": 1}))\n'
            )
            (package / '__main__.py').write_text(reader, encoding='utf-8')
            (support / 'lib_path').write_text(str(library) + '\n', encoding='utf-8')
            env = dict(os.environ, HOME=str(user_directory),
                       PYTHONPATH='/nonexistent/foreign-library', PYTHONHOME='/nonexistent/foreign-python')
            self.assertFalse((support / 'cache').exists())
            values = self.run_host(str(clip), env=env)
            self.assertEqual(values['metaValid'], '1', values.get('status'))
            self.assertEqual(values['camera'], 'Bootstrap test camera')
            self.assertEqual(float(values['colorTemp']), 4300)
            self.assertIn('scritti', values.get('status', ''))
            self.assertEqual(len(list((support / 'cache').glob('*.json'))), 1)


if __name__ == '__main__':
    unittest.main()
