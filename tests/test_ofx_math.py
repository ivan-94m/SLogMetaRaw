# SPDX-License-Identifier: GPL-3.0-or-later
"""The C++ maths of the plugin (gen/DevelopMath.h) matches tests/develop_model.py and tests/model."""
import math
import os
import random
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import develop_model as dm  # noqa: E402
from model import tone as T  # noqa: E402
from plugin_build import rosetta, test_bin  # noqa: E402

ZONES = T.ZONES
TONE_ORDER = (['toneContrast', 'toneHighlights', 'toneShadows', 'toneWhites', 'toneBlacks', 'toneVibrance',
               'toneSaturation', 'zonePivot'] + ['zone%sExp' % z for z in ZONES] + ['zone%sSat' % z for z in ZONES]
              + ['zone%sRange' % z for z in ZONES] + ['zone%sFalloff' % z for z in ZONES]
              + ['softClip', 'softClipLevel', 'softClipColor'])


def random_panel(rnd, strength):
    """A panel with each control moved with probability `strength`, anywhere in its range."""
    panel = {}
    for name in TONE_ORDER:
        lo, hi, default = T.CONTROLS[name]
        if rnd.random() < strength:
            panel[name] = float(rnd.random() < 0.5) if name == 'softClip' else rnd.uniform(lo, hi)
    return panel


def tone_values(panel):
    return [panel.get(n, T.CONTROLS[n][2]) for n in TONE_ORDER]


class OfxMath(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exe = test_bin('ofx_math_test')
        if not cls.exe:
            raise unittest.SkipTest('binari di test non compilabili qui')

    def run_exe(self, args, lines):
        return subprocess.run([self.exe] + args, input='\n'.join(lines) + '\n', capture_output=True, text=True,
                              check=True).stdout

    def test_no_fused_multiply_add_on_either_slice(self):
        """a*b+c with these values is 0 only when rounded twice: the x86_64 slice never fuses,
        so the arm64 one must not either, or the two builds of the plugin disagree."""
        probe = ['--fma', repr(1 + 2 ** -13), repr(1 - 2 ** -13), '-1']
        runs = [[self.exe]] + ([['arch', '-x86_64', self.exe]] if rosetta() else [])
        for cmd in runs:
            out = subprocess.run(cmd + probe, capture_output=True, text=True, check=True).stdout
            self.assertEqual(float(out), 0.0, ' '.join(cmd))

    def test_the_tone_policy_matches_the_model(self):
        """sm_set_tone (float32 fields computed in double) against model.tone.set_tone."""
        rnd = random.Random(11)
        cases = [({}, 2, 0, 1.0)] + [(random_panel(rnd, s), rnd.choice([0, 1, 2, 3, 5, 8]), rnd.choice([0, 1]),
                                      rnd.choice([1.0, 2.0 ** rnd.uniform(-3, 3)]))
                                     for s in (0.2, 0.5, 1.0) for _ in range(60)]
        out = self.run_exe(['--dump-tone'], [' '.join(repr(v) for v in [os_, cv, ex] + tone_values(p))
                                             for p, os_, cv, ex in cases])
        blocks = out.split('end\n')[:-1]
        self.assertEqual(len(blocks), len(cases))
        for (panel, os_, cv, ex), block in zip(cases, blocks):
            want = T.set_tone(panel, os_, bool(cv), ex)
            flat = dict(want, **{k: want[k] for k in T.CURVE_FIELDS})
            for line in block.strip().splitlines():
                name, *values = line.split()
                expected = flat[name] if isinstance(flat[name], list) else [flat[name]]
                self.assertEqual(len(values), len(expected), name)
                for a, b in zip(values, expected):
                    self.assertTrue(math.isclose(float(a), float(b), rel_tol=2e-6, abs_tol=1e-6),
                                    '%s: C++ %s, modello %s (pannello %s)' % (name, a, b, panel))

    def test_matches_model(self):
        rnd = random.Random(7)
        configs = [(0, 0, 0, 0), (0, 0, 1, 3), (8, 9, 8, 9), (6, 8, 0, 0), (10, 10, 1, 5), (0, 0, 2, 6)]
        V2F, F2V = (876 / 1023, 64 / 1023), (1023 / 876, -64 / 876)
        levels = [(0, 0, 0, 1.0, 0.0), (1, 8, 9) + V2F, (1, 8, 9) + F2V,
                  (1, 7, 9) + V2F, (1, 6, 8) + V2F, (1, 10, 10) + F2V]
        fcs = [(0,) + (0.0,) * 6, (0,) + (0.0,) * 6, (1,) + (0.0,) * 6, (4,) + (0.0,) * 6,
               (2,) + dm.fc_calibration(5600.0, 0.0), (3,) + dm.fc_calibration(5600.0, 0.0),
               (2,) + dm.fc_calibration(3200.0, 12.0), (3,) + dm.fc_calibration(8000.0, -8.0)]
        cases = []
        for ci, (ns, ng, os_, og) in enumerate(configs):
            for li, lvl in enumerate(levels):
                fc = fcs[(ci + li) % len(fcs)]
                for i in range(14):
                    # code values in range, plus the edges a real frame carries: black, super-whites,
                    # negative footroom and specular highlights far above white
                    rgb = [rnd.uniform(0.2, 0.7) for _ in range(3)] if i < 10 else \
                          [rnd.choice([0.0, -0.02, 0.95, 1.2, rnd.uniform(0.05, 0.99)]) for _ in range(3)]
                    # the white balance corners too: low Kelvin with green tint is where the guard works
                    shot = (rnd.choice([2000, 3200, 4000, 5600, 15000]), rnd.choice([0, 5, 15.17, -60, 99]),
                            rnd.choice([800, 2500]))
                    panel = random_panel(rnd, rnd.choice([0.0, 0.3, 1.0]))
                    kw = dict(temp=rnd.choice([rnd.uniform(2800, 7500), rnd.uniform(2000, 15000)]),
                              tint=rnd.choice([rnd.uniform(-20, 20), rnd.uniform(-100, 100)]),
                              ei=shot[2] * rnd.uniform(0.5, 2), level_fix=lvl[0], level_space=lvl[1],
                              level_gamma=lvl[2], level_gain=lvl[3], level_offset=lvl[4], fc_mode=fc[0],
                              fc_u=fc[1], fc_v=fc[2], fc_ku=fc[3], fc_kv=fc[4], fc_tu=fc[5], fc_tv=fc[6])
                    cases.append((rgb, ns, ng, os_, og, shot, kw, panel))
        lines = []
        for rgb, ns, ng, os_, og, shot, kw, panel in cases:
            head = rgb + [ns, ng, os_, og, *shot, kw['temp'], kw['tint'], kw['ei'], kw['level_fix'],
                          kw['level_space'], kw['level_gamma'], kw['level_gain'], kw['level_offset'],
                          kw['fc_mode'], kw['fc_u'], kw['fc_v'], kw['fc_ku'], kw['fc_kv'], kw['fc_tu'], kw['fc_tv']]
            lines.append(' '.join(repr(v) for v in head + tone_values(panel)))
        results = [[float(v) for v in l.split()] for l in self.run_exe([], lines).strip().splitlines()]
        self.assertEqual(len(results), len(cases))
        # float32 (C++) against float64 (model): 2e-4 on a value of order 1, relative beyond
        worst = worst_abs = 0.0
        where = None
        for (rgb, ns, ng, os_, og, shot, kw, panel), got in zip(cases, results):
            exp = dm.develop(rgb, ns, ng, shot=shot, out_space=os_, out_gamma=og, tone=panel, **kw)
            gamma = og if (os_, og) != (ns, ng) else ng
            for a, b in zip(exp, got):
                # near black a pure power curve turns one float32 ulp of light into 1e-4 of code value
                if abs(dm.decode1(a, gamma) - dm.decode1(b, gamma)) <= 2e-6:
                    continue
                err = abs(a - b) / max(1.0, abs(a))
                if err > worst:
                    worst, where = err, (rgb, ns, ng, os_, og, kw['fc_mode'], panel, exp, got)
                worst_abs = max(worst_abs, abs(a - b))
        self.assertLess(worst, 2e-4, 'max scaled difference %g (absolute %g) at %s' % (worst, worst_abs, where))


if __name__ == '__main__':
    unittest.main()
