# SPDX-License-Identifier: GPL-3.0-or-later
"""Load the built plugin in a miniature OpenFX host and run the actions Resolve runs.

This is the check that would have caught the two crashes we hit in DaVinci Resolve:
a duplicate parameter name, and a set of claimed names shared between the two
describeInContext calls (which left the second context with no parameters).
"""
import os
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

    def run_host(self, clip=None):
        run = subprocess.run([self.exe, BINARY] + ([clip] if clip else []), capture_output=True, text=True)
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


if __name__ == '__main__':
    unittest.main()
