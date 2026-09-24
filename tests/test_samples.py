# SPDX-License-Identifier: GPL-3.0-or-later
"""Reader regressions: sample clips (values verified against Catalyst Browse), sampling
order and limits on synthetic Sony clips, and parity on the real clips in ~/Downloads.

Run: python3 -m unittest discover -s tests   (from the project folder)
"""
import glob
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tests'))

from slogmetaraw import read_clip, DatalessError, extract, mp4, mxf, nrt  # noqa: E402
from slogmetaraw.plugin_cache import build_record  # noqa: E402
from slogmetaraw.resolve_io import build_fields  # noqa: E402
import clip_fixtures as fx  # noqa: E402

S = os.path.join(ROOT, 'samples')
CLIPS_DIR = os.environ.get('SLOGMETARAW_CLIPS') or os.path.expanduser('~/Downloads')


def clip(rel):
    p = os.path.join(S, rel)
    if not os.path.exists(p):
        raise unittest.SkipTest('sample missing: ' + rel)
    return read_clip(p)


def render_values(r):
    """The record fields the node renders with."""
    return {k: v for k, v in build_record(r).items()
            if k == 'supported' or k.startswith(('shot_', 'cam_', 'level_'))}


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
        """A renamed clip without M01.XML takes the NRT XML from inside the MP4."""
        r = clip('Sony a6300/20191028_a63A01_C0054.MP4')
        self.assertIsNone(r.get('sidecar'))
        self.assertEqual(r['nrt_source'], 'embedded')
        self.assertEqual(r['meta']['model'], 'ILCE-6300')
        self.assertTrue(r['meta'].get('start_tc'))


class SampleOrder(unittest.TestCase):
    @staticmethod
    def even_spread(n, fps, interval, max_samples):
        """The 1.1 selection, kept as the reference for which frames are sampled."""
        step = max(1, int(round(fps * interval)))
        idx = list(range(0, n, step))
        if idx[-1] != n - 1:
            idx.append(n - 1)
        if len(idx) > max_samples:
            k = (len(idx) - 1) / (max_samples - 1)
            idx = sorted({idx[int(round(i * k))] for i in range(max_samples)})
        return idx

    def test_a_single_sample_is_the_first_frame(self):
        """One sample reads frame 0, never the last frame."""
        self.assertEqual(extract._sample_indices(1000, 25, 1, 1), [0])

    def test_first_and_last_frames_come_first(self):
        """The first two reads are frames 0 and n-1, so a cut-short sampling keeps both."""
        for n, cap in ((1000, 8), (1000, 24), (90000, 120), (30, 24), (2, 8)):
            with self.subTest(n=n, cap=cap):
                self.assertEqual(extract._sample_indices(n, 25, 1, cap)[:2], [0, n - 1])

    def test_never_more_than_asked_and_no_repeats(self):
        """At most max_samples distinct indices inside the clip."""
        for n in (1, 2, 3, 50, 999, 90000):
            for cap in (1, 2, 8, 24, 120):
                idx = extract._sample_indices(n, 25, 1, cap)
                self.assertLessEqual(len(idx), cap)
                self.assertEqual(len(set(idx)), len(idx))
                self.assertTrue(all(0 <= i < n for i in idx))

    def test_same_frames_as_the_even_spread(self):
        """Reordering changes when frames are read, not which ones."""
        for n, cap in ((1000, 8), (1000, 24), (90000, 120), (40, 24)):
            with self.subTest(n=n, cap=cap):
                self.assertEqual(sorted(extract._sample_indices(n, 25, 1, cap)),
                                 self.even_spread(n, 25, 1, cap))

    def test_coarse_to_fine(self):
        """Halves come before quarters and quarters before eighths."""
        self.assertEqual(extract._coarse_to_fine(list(range(9))), [0, 8, 4, 2, 6, 1, 3, 5, 7])


class Synthetic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def path(self, name):
        return os.path.join(self.tmp, name)


class SyntheticMp4(Synthetic):
    FRAMES = 2500   # 100 s at 25 fps: more samples than any limit

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mp4 = os.path.join(cls.tmp, 'C0001.MP4')
        cls.samples = fx.build_mp4(cls.mp4, frames=cls.FRAMES)

    def test_values(self):
        """The fixture reads as an S-Log3 clip with the camera's first-frame values."""
        rec = build_record(read_clip(self.mp4))
        self.assertEqual((rec['supported'], rec['cam_space'], rec['cam_gamma']), (1, 8, 9))
        self.assertEqual((rec['shot_ei'], rec['shot_temp']), (3200, 3000))

    def test_cache_sampling_costs_few_reads(self):
        """With 8 samples the whole clip costs at most 20 reads, first and last frame included."""
        r = read_clip(self.mp4, max_samples=8)
        self.assertLessEqual(r['reads'], 20)
        self.assertEqual(r['sampling']['read'], 8)
        self.assertTrue(r['sampling']['partial'])
        wb = r['changes']['white_balance_k']
        self.assertEqual((wb['first'], wb['last']), (3000, 3000 + self.FRAMES - 1))

    def test_full_sampling_is_not_partial(self):
        """24 samples are the script's complete reading."""
        r = read_clip(self.mp4, max_samples=24)
        self.assertEqual(r['sampling']['read'], 24)
        self.assertFalse(r['sampling']['partial'])
        rec = build_record(r)
        self.assertEqual((rec['samples_read'], rec['samples_planned'], rec['partial']), (24, 24, 0))

    def test_deadline_stops_sampling_but_keeps_first_and_last(self):
        """A slow disk (50 ms per sample) and 0.3 s left: back in time, partial, exact ends."""
        start, end = self.samples
        pread = mp4.CountingFile._pread

        def slow(f, pos, n):
            if start <= pos < end:
                time.sleep(0.05)
            return pread(f, pos, n)

        with mock.patch.object(mp4.CountingFile, '_pread', slow):
            began = time.monotonic()
            r = read_clip(self.mp4, max_samples=24, deadline=began + 0.3)
            elapsed = time.monotonic() - began
        self.assertLess(elapsed, 0.45)
        self.assertTrue(r['sampling']['partial'])
        self.assertLess(r['sampling']['read'], r['sampling']['planned'])
        wb = r['changes']['white_balance_k']
        self.assertEqual((wb['first'], wb['last']), (3000, 3000 + self.FRAMES - 1))
        self.assertIn('non verificato', build_record(dict(r, changes={}))['fps'])
        details = dict(r['sections'])['VARIAZIONI DURANTE LA CLIP']
        self.assertIn('campionamento parziale', details[0][1])

    def test_one_clip_reads_quickly(self):
        """The only wall-clock guard, deliberately loose."""
        began = time.monotonic()
        read_clip(self.mp4, max_samples=8)
        self.assertLess(time.monotonic() - began, 0.2)

    def test_sidecar_is_found_without_listing_the_folder(self):
        """<stem>M01.XML is opened directly: the folder is never listed."""
        clip_path = self.path('C0002.MP4')
        shutil.copyfile(self.mp4, clip_path)
        with open(self.path('C0002M01.XML'), 'w', encoding='utf-8') as fh:
            fh.write(fx.NRT_XML.format(frames=self.FRAMES).replace('ILME-FX6V', 'ILME-FX30'))
        with mock.patch('os.listdir', side_effect=AssertionError('listdir')):
            r = read_clip(clip_path, max_samples=2)
        self.assertEqual(r['nrt_source'], 'sidecar')
        self.assertEqual(r['meta']['model'], 'ILME-FX30')


class SyntheticMxf(Synthetic):
    FRAMES = 250

    def build(self, name, **kw):
        p = self.path(name)
        fx.build_mxf(p, frames=kw.pop('frames', self.FRAMES), picture=kw.pop('picture', 20 * 1024), **kw)
        return p

    def test_essence_beyond_the_first_4_mb(self):
        """5 MB of header metadata: the partition pack still leads to the metadata, SPS included."""
        p = self.build('long.MXF')
        with mp4.CountingFile(p) as f:
            self.assertIsNone(mxf.find_rtmd(f, 0))   # the 1.1 head window finds nothing
        r = read_clip(p, max_samples=8)
        rec = build_record(r)
        self.assertEqual((rec['supported'], rec['cam_space'], rec['cam_gamma']), (1, 8, 9))
        self.assertEqual((rec['shot_ei'], rec['shot_temp']), (3200, 3000))
        self.assertEqual((r['meta']['v_width'], r['meta']['v_profile']), (1920, 'High422'))
        self.assertLess(r['bytes_read'], 12 * 1024 * 1024)
        self.assertLessEqual(r['reads'], 24)

    def test_index_gives_the_exact_last_frame(self):
        """With an index table (entries or constant size) the last sample is the last frame."""
        for index in ('vbe', 'cbe'):
            with self.subTest(index=index):
                r = read_clip(self.build('%s.MXF' % index, index=index), max_samples=8)
                wb = r['changes']['white_balance_k']
                self.assertEqual((wb['first'], wb['last']), (3000, 3000 + self.FRAMES - 1))
                self.assertEqual(r['sampling']['read'], 8)

    def test_without_index_the_windows_are_scanned(self):
        """No index: first package plus byte-scan windows, as in 1.1."""
        r = read_clip(self.build('noindex.MXF', index=None), max_samples=24)
        self.assertEqual(build_record(r)['supported'], 1)
        self.assertGreaterEqual(r['sampling']['read'], 2)
        self.assertIn('white_balance_k', r['changes'])

    def test_a_start_code_in_the_header_is_not_the_sps(self):
        """An SPS-like start code in header metadata is ignored: the SPS comes from the picture."""
        p = self.path('junk.MXF')
        fx.build_mxf(p, frames=10, picture=20 * 1024, header_fill=64 * 1024,
                     header_junk=b'\x00\x00\x01\x67\x42\x00\x0a\x00\x00\x01')
        r = read_clip(p)
        self.assertEqual((r['meta']['v_width'], r['meta']['v_height']), (1920, 1080))

    def test_the_nrt_xml_names_the_curve_without_anc(self):
        """No ANC at all: s-gamut3-cine / s-log3-cine from the XML still make a supported record."""
        r = read_clip(self.build('noanc.MXF', anc=False, frames=20))
        rec = build_record(r)
        self.assertEqual((rec['supported'], rec['cam_space'], rec['cam_gamma']), (1, 8, 9))
        self.assertEqual(rec['level_required'], 1)   # Full, as the curve requires
        self.assertTrue(any('non trovati' in w for w in r['warnings']))

    def test_nrt_names(self):
        """Every NRT gamma/primaries pair maps to the rtmd names, and only S-Log does."""
        cases = {('s-log3-cine', 's-gamut3-cine'): ('S-Gamut3.Cine/S-Log3', 'S-Gamut3.Cine'),
                 ('s-log3-cine', None): ('S-Gamut3.Cine/S-Log3', 'S-Gamut3.Cine'),
                 ('s-log3', 's-gamut3'): ('S-Gamut3/S-Log3', 'S-Gamut3'),
                 ('S-Log3', 'S-Gamut3-Cine'): ('S-Gamut3.Cine/S-Log3', 'S-Gamut3.Cine'),
                 ('s-log3', None): (None, None),
                 ('s-log2', 's-gamut'): ('S-Log2', 'S-Gamut'),
                 ('s-log2', None): ('S-Log2', None),
                 ('rec709', 'rec709'): (None, None),
                 (None, None): (None, None)}
        for (gamma, prim), want in cases.items():
            with self.subTest(gamma=gamma, primaries=prim):
                self.assertEqual(nrt.capture_space({'xml_gamma': gamma, 'xml_primaries': prim}), want)


def real_clips():
    names = glob.glob(os.path.join(CLIPS_DIR, '*'))
    return sorted(p for p in names if p.lower().endswith(('.mp4', '.mxf')) and os.path.isfile(p))


class RealClips(unittest.TestCase):
    """Parity on the user's clips; skipped when the folder has none."""

    def setUp(self):
        self.clips = real_clips()
        if not self.clips:
            self.skipTest('nessuna clip in %s' % CLIPS_DIR)

    def read(self, p, **kw):
        try:
            return read_clip(p, **kw)
        except (DatalessError, PermissionError):   # iCloud placeholder, or no access granted
            return None

    def test_8_and_120_samples_render_the_same(self):
        """supported, shot_*, cam_* and level_* do not depend on how many frames are sampled."""
        for p in self.clips:
            with self.subTest(clip=os.path.basename(p)):
                r8, r120 = self.read(p, max_samples=8), self.read(p, max_samples=120)
                if r8 is None:
                    continue
                self.assertEqual(render_values(r8), render_values(r120))

    def test_sony_clips_cost_few_reads_for_the_plugin(self):
        """--cache sampling: at most 20 reads for an MP4, 24 for an MXF."""
        for p in self.clips:
            r = self.read(p, max_samples=8)
            if r is None or not r['sampling']['total']:
                continue   # not a Sony clip: nothing sampled
            with self.subTest(clip=os.path.basename(p)):
                self.assertLessEqual(r['reads'], 24 if r['container'] == 'MXF' else 20)

    def test_look_lut_is_read_only_on_request(self):
        """The ~434 KB 'Look Control data' item stays on disk unless asked for."""
        for p in self.clips:
            r = self.read(p, max_samples=2)
            if r is None or r['container'] != 'MP4':
                continue
            with_lut = self.read(p, max_samples=2, lut=True)
            if not with_lut.get('embedded_lut'):
                continue
            with self.subTest(clip=os.path.basename(p)):
                self.assertNotIn('embedded_lut', r)
                self.assertLess(r['bytes_read'] + 256 * 1024, with_lut['bytes_read'])
            return
        self.skipTest('nessuna clip con LUT incorporata')


if __name__ == '__main__':
    unittest.main()
