# SPDX-License-Identifier: GPL-3.0-or-later
"""The C++ math used by the SLogMetaRaw plugin must match tests/develop_model.py."""
import os
import random
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import develop_model as dm  # noqa: E402


class OfxMath(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('clang++'):
            raise unittest.SkipTest('clang++ not available')
        cls.tmp = tempfile.mkdtemp()
        cls.exe = os.path.join(cls.tmp, 'ofx_math_test')
        subprocess.run(['clang++', '-std=c++17', '-O2', '-o', cls.exe,
                        os.path.join(ROOT, 'tests', 'ofx_math_test.cpp')], check=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_matches_model(self):
        rnd = random.Random(7)
        cases = []
        configs = [(0, 0, 0, 0), (0, 0, 1, 3), (8, 9, 8, 9), (6, 8, 0, 0), (10, 10, 1, 5), (0, 0, 2, 6)]
        for ns, ng, os_, og in configs:
            for _ in range(40):
                rgb = [rnd.uniform(0.2, 0.7) for _ in range(3)]
                shot = (rnd.choice([3200, 4000, 5600]), rnd.choice([0, 5]), rnd.choice([800, 2500]))
                kw = dict(temp=rnd.uniform(2800, 7500), tint=rnd.uniform(-20, 20), ei=shot[2] * rnd.uniform(0.5, 2),
                          shadows=rnd.uniform(-0.5, 0.5), highlights=rnd.uniform(-0.5, 0.5),
                          contrast=rnd.uniform(-0.3, 0.3), saturation=rnd.uniform(-0.3, 0.3), boost=rnd.uniform(0, 0.5))
                cases.append((rgb, ns, ng, os_, og, shot, kw))
        lines = []
        for rgb, ns, ng, os_, og, shot, kw in cases:
            lines.append(' '.join(str(v) for v in rgb + [ns, ng, os_, og, *shot, kw['temp'], kw['tint'], kw['ei'],
                                                          kw['shadows'], kw['highlights'], kw['contrast'],
                                                          kw['saturation'], kw['boost']]))
        out = subprocess.run([self.exe], input='\n'.join(lines), capture_output=True, text=True, check=True).stdout
        results = [[float(v) for v in l.split()] for l in out.strip().splitlines()]
        self.assertEqual(len(results), len(cases))
        worst = 0.0
        for (rgb, ns, ng, os_, og, shot, kw), got in zip(cases, results):
            exp = dm.develop(rgb, ns, ng, shot=shot, out_space=os_, out_gamma=og, **kw)
            worst = max(worst, max(abs(a - b) for a, b in zip(exp, got)))
        self.assertLess(worst, 2e-4, 'max difference %g' % worst)


if __name__ == '__main__':
    unittest.main()
