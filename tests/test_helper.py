# SPDX-License-Identifier: GPL-3.0-or-later
"""The --helper mode feeds the script window: one path in, one JSON line out."""
import json
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Helper(unittest.TestCase):
    def run_helper(self, lines):
        proc = subprocess.run([sys.executable, '-m', 'slogmetaraw', '--helper'],
                              input='\n'.join(lines) + '\n', capture_output=True,
                              text=True, cwd=ROOT, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return [json.loads(l) for l in proc.stdout.splitlines()]

    def test_missing_file_reports_error(self):
        out = self.run_helper(['/percorso/inesistente.MP4'])
        self.assertEqual(len(out), 1)
        self.assertFalse(out[0]['ok'])
        self.assertEqual(out[0]['kind'], 'error')
        self.assertIn('inesistente', out[0]['error'])

    def test_blank_lines_are_ignored(self):
        out = self.run_helper(['', '   '])
        self.assertEqual(out, [])


if __name__ == '__main__':
    unittest.main()
