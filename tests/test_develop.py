# SPDX-License-Identifier: GPL-3.0-or-later
"""Camera values, plugin records and the develop math model (tests/develop_model.py)."""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tests'))

from slogmetaraw import read_clip, camera, plugin_cache  # noqa: E402
import develop_model as dm  # noqa: E402


def sample(rel):
    p = os.path.join(ROOT, 'samples', rel)
    if not os.path.exists(p):
        raise unittest.SkipTest('sample missing: ' + rel)
    return read_clip(p)


class CameraValues(unittest.TestCase):
    def test_fx30(self):
        m = sample('Sony FX30/F002C005_260717TL.MP4')['meta']
        self.assertEqual(camera.shot_values(m), (4000, 0.0, 4000, False))
        self.assertEqual(camera.camera_space(m), ('S-Gamut3.Cine', 'SLog3'))

    def test_a6300_estimated_wb(self):
        m = sample('Sony a6300/20191028_a63A01_C0054.MP4')['meta']
        k, tint, ei, estimated = camera.shot_values(m)
        self.assertEqual((k, ei, estimated), (5600, 3200, True))  # Daylight preset, no Kelvin recorded
        self.assertEqual(camera.camera_space(m), ('S-Gamut', 'SLog2'))


class PluginRecord(unittest.TestCase):
    def test_fnv_matches_plugin(self):
        # same hash as fnv1a64() in ofx/SLogMetaRaw/SLogMetaRaw.cpp
        self.assertEqual(plugin_cache.fnv1a64(''), 'cbf29ce484222325')
        self.assertEqual(plugin_cache.fnv1a64('a'), 'af63dc4c8601ec8c')

    def test_record_fields(self):
        r = sample('Sony FX30/F002C005_260717TL.MP4')
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(plugin_cache, 'CACHE_DIR', tmp):
            path = plugin_cache.write_cache(r)
            with open(path, encoding='utf-8') as fh:
                rec = json.load(fh)
        self.assertEqual(rec['camera_name'], 'Sony ILME-FX30 (FX30)')
        self.assertEqual((rec['shot_temp'], rec['shot_ei'], rec['supported']), (4000, 4000, 1))
        self.assertEqual((rec['cam_space'], rec['cam_gamma']), (8, 9))
        self.assertEqual(rec['iris'], 'f/2.8')
        self.assertIn('Full Scaled Code', rec['color'])


class Model(unittest.TestCase):
    px = [0.45, 0.40, 0.35]

    def test_identity_at_camera_values(self):
        for node in ((0, 0), (8, 9)):
            out = dm.develop(self.px, *node, shot=(4000, 0, 4000))
            for a, b in zip(out, self.px):
                self.assertAlmostEqual(a, b, places=6)

    def test_exposure_doubles_linear(self):
        g = [dm.encode1(0.18, 9)] * 3
        out = dm.develop(g, 8, 9, shot=(4000, 0, 800), ei=1600)
        self.assertAlmostEqual(dm.decode1(out[1], 9), 0.36, places=5)

    def test_wb_direction(self):
        g = [dm.encode1(0.18, 9)] * 3
        warm = [dm.decode1(c, 9) for c in dm.develop(g, 8, 9, shot=(4000, 0, 800), temp=6500)]
        self.assertGreater(warm[0], warm[2])

    def test_slog2_levels_match_sony(self):
        self.assertAlmostEqual((dm.encode1(0.18, 8) * 1023 - 64) / 876, 0.323, places=3)

    def test_gamma_choice_converts_like_cst(self):
        g = [dm.encode1(0.18, 0)] * 3
        out = dm.develop(g, 0, 0, shot=(4000, 0, 4000), out_gamma=3)
        self.assertAlmostEqual(out[1], 0.18 ** (1 / 2.4), places=4)


if __name__ == '__main__':
    unittest.main()
