# SPDX-License-Identifier: GPL-3.0-or-later
"""The constants of the plugin's tone maths (ofx/SLogMetaRaw/math) equal those of the Python model.

If they drifted apart the parity tests would still compare the two against each other, each one right
by its own numbers. Every SM_CONST of the headers must be found and checked."""
import glob
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tests'))
from model import tone as T  # noqa: E402

MATH = os.path.join(ROOT, 'ofx', 'SLogMetaRaw', 'math')
SCALAR = re.compile(r'SM_CONST float (SM_(?:T5|FC)_\w+)\s*=\s*([-+0-9.eE]+)f;')
ARRAY = re.compile(r'SM_CONST float (SM_(?:T5|FC)_\w+)\[\d+\]\s*=\s*\{([^}]*)\};', re.S)
DEFINE = re.compile(r'#define (SM_T5_\w+) (\d+)')
HOST = re.compile(r'static const double (SM_T5_\w+) = ([^;]+);')


def headers():
    text = ''
    for path in sorted(glob.glob(os.path.join(MATH, '*.h'))):
        with open(path, encoding='utf-8') as fh:
            text += fh.read()
    return text


class ConstantsAgree(unittest.TestCase):
    def setUp(self):
        self.src = headers()

    def test_every_scalar_constant(self):
        found = SCALAR.findall(self.src)
        self.assertGreaterEqual(len(found), 20)
        for name, value in found:
            self.assertTrue(hasattr(T, name), 'il modello non ha %s' % name)
            self.assertAlmostEqual(float(value), getattr(T, name), delta=abs(getattr(T, name)) * 1e-8 + 1e-12,
                                   msg=name)

    def test_every_array_constant(self):
        found = ARRAY.findall(self.src)
        self.assertEqual(sorted(n for n, _ in found), ['SM_FC_ZONE_TINT', 'SM_T5_ZONE_DIR'])
        for name, body in found:
            values = [float(v.strip().rstrip('f')) for v in body.split(',') if v.strip()]
            model = getattr(T, name)
            flat = [x for row in model for x in row] if isinstance(model[0], tuple) else list(model)
            self.assertEqual(values, flat, name)

    def test_the_slot_layout_and_host_limits(self):
        for name, value in DEFINE.findall(self.src):
            self.assertEqual(int(value), getattr(T, name), name)
        host = dict(HOST.findall(self.src))
        self.assertGreaterEqual(len(host), 6)
        for name, expr in host.items():
            self.assertAlmostEqual(eval(expr), getattr(T, name), places=12, msg=name)
        self.assertIn('SM_T5_ZONE_SLOT[4] = { 4, 6, 3, 0 }', self.src)
        self.assertEqual(T.ZONE_SLOT, (4, 6, 3, 0))


if __name__ == '__main__':
    unittest.main()
