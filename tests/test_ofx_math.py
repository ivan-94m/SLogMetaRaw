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
        # the data level stage: off, video->full and full->video, applied both in the
        # node's own encoding and through the round-trip from another one (RCM/ACES)
        V2F = (876 / 1023, 64 / 1023)
        F2V = (1023 / 876, -64 / 876)
        levels = [(0, 0, 0, 1.0, 0.0), (1, 8, 9) + V2F, (1, 8, 9) + F2V,
                  (1, 7, 9) + V2F, (1, 6, 8) + V2F, (1, 10, 10) + F2V]
        # the false colour views, with the calibration buildParams computes for them
        fcs = [(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0), (1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
               (2,) + dm.fc_calibration(5600.0, 0.0), (3,) + dm.fc_calibration(5600.0, 0.0),
               (2,) + dm.fc_calibration(3200.0, 12.0), (3,) + dm.fc_calibration(8000.0, -8.0)]
        for ns, ng, os_, og in configs:
            for lvl in levels:
                fc = fcs[(configs.index((ns, ng, os_, og)) + levels.index(lvl)) % len(fcs)]
                for _ in range(12):
                    rgb = [rnd.uniform(0.2, 0.7) for _ in range(3)]
                    shot = (rnd.choice([3200, 4000, 5600]), rnd.choice([0, 5]), rnd.choice([800, 2500]))
                    kw = dict(temp=rnd.uniform(2800, 7500), tint=rnd.uniform(-20, 20), ei=shot[2] * rnd.uniform(0.5, 2),
                              shadows=rnd.uniform(-0.5, 0.5), highlights=rnd.uniform(-0.5, 0.5),
                              contrast=rnd.uniform(-0.3, 0.3), saturation=rnd.uniform(-0.3, 0.3),
                              boost=rnd.uniform(0, 0.5),
                              level_fix=lvl[0], level_space=lvl[1], level_gamma=lvl[2],
                              level_gain=lvl[3], level_offset=lvl[4],
                              fc_mode=fc[0], fc_u=fc[1], fc_v=fc[2], fc_ku=fc[3],
                              fc_kv=fc[4], fc_tu=fc[5], fc_tv=fc[6],
                              chroma_recover=rnd.uniform(-1.0, 1.0))
                    cases.append((rgb, ns, ng, os_, og, shot, kw))
        lines = []
        for rgb, ns, ng, os_, og, shot, kw in cases:
            lines.append(' '.join(str(v) for v in rgb + [ns, ng, os_, og, *shot, kw['temp'], kw['tint'], kw['ei'],
                                                          kw['shadows'], kw['highlights'], kw['contrast'],
                                                          kw['saturation'], kw['boost'],
                                                          kw['level_fix'], kw['level_space'], kw['level_gamma'],
                                                          kw['level_gain'], kw['level_offset'],
                                                          kw['fc_mode'], kw['fc_u'], kw['fc_v'], kw['fc_ku'],
                                                          kw['fc_kv'], kw['fc_tu'], kw['fc_tv'],
                                                          kw['chroma_recover']]))
        out = subprocess.run([self.exe], input='\n'.join(lines), capture_output=True, text=True, check=True).stdout
        results = [[float(v) for v in l.split()] for l in out.strip().splitlines()]
        self.assertEqual(len(results), len(cases))
        # float32 (C++) against float64 (model): 2e-4 on a value of order 1, scaled
        # up for the pixels the fuzz pushes to a magnitude of hundreds, where the same
        # relative error is just rounding and not a difference in the maths.
        worst = worst_abs = 0.0
        for (rgb, ns, ng, os_, og, shot, kw), got in zip(cases, results):
            exp = dm.develop(rgb, ns, ng, shot=shot, out_space=os_, out_gamma=og, **kw)
            for a, b in zip(exp, got):
                worst_abs = max(worst_abs, abs(a - b))
                worst = max(worst, abs(a - b) / max(1.0, abs(a)))
        self.assertLess(worst, 2e-4, 'max scaled difference %g (absolute %g)' % (worst, worst_abs))


if __name__ == '__main__':
    unittest.main()
