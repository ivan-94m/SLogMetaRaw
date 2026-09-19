# SPDX-License-Identifier: GPL-3.0-or-later
"""Regression check on the sample clips (values verified against Catalyst Browse).

Run: python3 -m unittest discover -s tests   (from the project folder)
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from slogmetaraw import read_clip  # noqa: E402
from slogmetaraw.resolve_io import build_fields  # noqa: E402

S = os.path.join(ROOT, 'samples')


def clip(rel):
    p = os.path.join(S, rel)
    if not os.path.exists(p):
        raise unittest.SkipTest('sample missing: ' + rel)
    return read_clip(p)


class FX6(unittest.TestCase):
    def test_matches_catalyst(self):
        r = clip('Sony FX6/A002C011_251223LK.MXF')
        d, m = r['display'], r['meta']
        self.assertEqual(d['iris_fnumber'], '2.81')
        self.assertEqual(d['focus_distance_m'], '2.953 m')
        self.assertEqual(d['focal_length_mm'], '10 mm')
        self.assertEqual(d['focal_length_35mm'], '11.1 mm')
        self.assertEqual(m['iso'], 800)
        self.assertEqual(m['exposure_index'], 800)
        self.assertEqual(d['white_balance_k'], '5500 K')
        self.assertEqual(m['tint'], 0)
        self.assertEqual(d['master_black_level'], '4.0 %')
        self.assertEqual(m['luminance_code_range'], 'Full Scaled Code')
        self.assertEqual(m['color_space'], 'S-Gamut3.Cine/S-Log3')
        self.assertEqual(m['start_tc'], '19:10:07:19')
        self.assertEqual(m['end_tc'], '19:10:12:11')
        self.assertEqual(m['duration_tc'], '00:00:04:17')
        self.assertEqual(m['firmware'], '5.01')
        self.assertEqual(build_fields(r)['Camera Aperture'], 'F2.8')


class FX30(unittest.TestCase):
    def test_values(self):
        r = clip('Sony FX30/F002C005_260717TL.MP4')
        m = r['meta']
        self.assertEqual(m['model'], 'ILME-FX30')
        self.assertEqual(m['lens'], 'LAOWA FFII 10mm F2.8 C D Dreame')
        self.assertAlmostEqual(m['iris_fnumber'], 2.81, places=2)
        self.assertEqual(m['iso'], 2500)
        self.assertEqual(m['exposure_index'], 4000)
        self.assertEqual(m['white_balance_k'], 4000)
        self.assertEqual(m['color_space'], 'S-Gamut3.Cine/S-Log3')
        self.assertEqual(m['luminance_code_range'], 'Full Scaled Code')
        self.assertTrue(m['v_full_range'])
        self.assertIn('shutter_angle', r['changes'])
        self.assertLess(r['bytes_read'], 2 * 1024 * 1024)


class A6300(unittest.TestCase):
    def test_values(self):
        r = clip('Sony a6300/C0004.MP4')
        m = r['meta']
        self.assertEqual(m['model'], 'ILCE-6300')
        self.assertEqual(m['color_space'], 'S-Gamut/S-Log2')
        self.assertEqual(m['iso'], 800)
        self.assertEqual(m['lighting_preset'], 'Other')
        self.assertEqual(m['recording_time'], '2024-12-09T07:20:18+01:00')
        self.assertNotIn('white_balance_k', m)
        self.assertNotIn('serial', m)  # 4294967295 = not provided

    def test_embedded_xml_only(self):
        # renamed clip without M01.XML sidecar: NRT XML must come from inside the MP4
        r = clip('Sony a6300/20191028_a63A01_C0054.MP4')
        self.assertIsNone(r.get('sidecar'))
        self.assertEqual(r['nrt_source'], 'embedded')
        self.assertEqual(r['meta']['model'], 'ILCE-6300')
        self.assertTrue(r['meta'].get('start_tc'))


if __name__ == '__main__':
    unittest.main()
