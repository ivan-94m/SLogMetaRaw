# SPDX-License-Identifier: GPL-3.0-or-later
"""The Metal kernel of SLogMetaRaw (compiled at runtime, like Resolve does) must match the CPU path."""
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OFX = os.path.join(ROOT, 'ofx', 'SLogMetaRaw')


class Metal(unittest.TestCase):
    def test_kernel_matches_cpu(self):
        if not shutil.which('clang++') or not os.path.exists(os.path.join(OFX, 'DevelopMathSource.inc')):
            self.skipTest('build the plugin first (make in ofx/SLogMetaRaw)')
        tmp = tempfile.mkdtemp()
        try:
            exe = os.path.join(tmp, 'metal_test')
            subprocess.run(['clang++', '-std=c++17', '-fno-objc-arc', '-O2', '-I', OFX,
                            os.path.join(ROOT, 'tests', 'metal_test.mm'), os.path.join(OFX, 'MetalKernel.mm'),
                            '-framework', 'Metal', '-framework', 'Foundation', '-o', exe],
                           check=True, capture_output=True)
            out = subprocess.run([exe], capture_output=True, text=True).stdout.strip()
            if out == 'NO_DEVICE':
                self.skipTest('no Metal device')
            self.assertTrue(out.startswith('MAXDIFF'), out)
            self.assertLess(float(out.split()[1]), 2e-4)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
