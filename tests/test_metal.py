# SPDX-License-Identifier: GPL-3.0-or-later
"""The Metal kernel (compiled at runtime, as Resolve does) matches the CPU path."""
import subprocess
import unittest

from plugin_build import test_bin


class Metal(unittest.TestCase):
    def test_kernel_matches_cpu(self):
        exe = test_bin('metal_test')
        if not exe:
            self.skipTest('binari di test non compilabili qui')
        out = subprocess.run([exe], capture_output=True, text=True).stdout.strip()
        if out == 'NO_DEVICE':
            self.skipTest('no Metal device')
        self.assertTrue(out.startswith('MAXDIFF'), out)
        fields = out.split()
        self.assertLess(float(fields[1]), 2e-4)
        self.assertEqual(float(fields[3]), 0.0, 'il kernel Metal contrae a*b+c in una FMA')


if __name__ == '__main__':
    unittest.main()
