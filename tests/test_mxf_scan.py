# SPDX-License-Identifier: GPL-3.0-or-later
"""Finding the acquisition metadata in an MXF, wherever the file put it.

The bug these guard: on a 97 minute 4K FX6 clip the node came up with every
control greyed out. The scanner looked for the ST 436 ANC element in a fixed 4 MiB
window starting at byte 0, and on that clip the first essence byte is further in
than that - an index table carries roughly one entry per frame, so it grows with
the take. Having missed it, the reader returned immediately, skipping the twelve
other windows it was about to read anyway.

Three consequences followed, all of them visible in the panel: the shooting values
were absent, the colour profile string was empty, and an empty profile makes
camera_space() raise, which sets supported = 0, which disables every slider.

There is no copy of that clip - it is tens of gigabytes. What matters about it is
its shape, and tests/mxf_fixture.py writes that shape in a few megabytes.
"""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tests'))

import mxf_fixture as fixture  # noqa: E402
from slogmetaraw import mxf, rtmd, camera, plugin_cache  # noqa: E402
from slogmetaraw.datalevel import FULL, VIDEO, gamma_scale  # noqa: E402
from slogmetaraw.extract import _color_space  # noqa: E402
from slogmetaraw.mp4 import CountingFile  # noqa: E402


class Fixture(unittest.TestCase):
    def build(self, **kw):
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: [os.remove(os.path.join(d, n)) for n in os.listdir(d)]
                        and os.rmdir(d) or os.path.isdir(d) and os.rmdir(d))
        info = fixture.build(os.path.join(d, 'clip.mxf'), **kw)
        f = CountingFile(info['path'])
        self.addCleanup(f.close)
        return f, info


class Structure(Fixture):
    def test_the_partition_pack_says_where_the_essence_starts(self):
        f, info = self.build()
        part = mxf.partition_at(f, 0)
        self.assertEqual(part['kind'], 'header')
        self.assertEqual(part['essence'], info['essence'])
        self.assertGreater(part['essence'], 4 * 1024 * 1024,
                           'la fixture deve riprodurre il caso: essenza oltre i 4 MiB')

    def test_offsets_are_64_bit(self):
        """A 97 minute 4K clip is tens of gigabytes, so every partition offset is
        past 2^32. Checked without writing a 70 GB file: the field is what matters."""
        pack = fixture.partition_pack(fixture.HEADER_PARTITION_KEY,
                                      footer=70_000_000_000, header_bytes=8, index_bytes=0)

        class Fake:
            size = 70_000_000_100

            def read_at(self, pos, n):
                return pack[pos:pos + n]

        part = mxf.partition_at(Fake(), 0)
        self.assertEqual(part['footer'], 70_000_000_000)

    def test_the_random_index_pack_lists_the_partitions(self):
        f, info = self.build()
        offsets = mxf.partition_offsets(f)
        self.assertIn(0, offsets)
        self.assertIn(info['footer'], offsets)

    def test_a_file_without_a_rip_is_not_an_error(self):
        """A clip still being written has no Random Index Pack. The scan falls back
        to the header partition, which is enough."""
        f, info = self.build(with_rip=False)
        self.assertEqual(mxf.partition_offsets(f), [])
        payload, at, _tried = mxf.find_acquisition(f, duration_s=5.0)
        self.assertIsNotNone(payload)
        self.assertEqual(at, info['essence'])

    def test_the_scan_window_follows_the_bitrate(self):
        f, _ = self.build()
        self.assertEqual(mxf.scan_window(f, None), mxf.WINDOW)
        self.assertGreaterEqual(mxf.scan_window(f, 0.5), mxf.WINDOW)
        self.assertLessEqual(mxf.scan_window(f, 1e-9), mxf.WINDOW_MAX)


class FindingIt(Fixture):
    def values(self, payload):
        return rtmd.values(rtmd.decode(payload))

    def test_the_old_blind_window_is_what_missed_it(self):
        """Kept as the reason the scan was rewritten rather than widened: a fixed
        window from byte 0 does not reach the essence on this shape of file."""
        f, _ = self.build()
        self.assertIsNone(mxf.find_rtmd(f, 0, mxf.WINDOW))

    def test_it_is_found_where_the_file_says_the_essence_is(self):
        f, info = self.build()
        payload, at, tried = mxf.find_acquisition(f, duration_s=5.0)
        self.assertIsNotNone(payload)
        self.assertEqual(at, info['essence'])
        self.assertEqual(len(tried), 1, 'doveva bastare il primo tentativo')
        v = self.values(payload)
        self.assertEqual(v['white_balance_k'], 5600)
        self.assertEqual(v['tint'], 15.17)
        self.assertEqual(v['exposure_index'], 800)
        self.assertEqual(v['iso'], 12800)
        self.assertEqual(v['capture_gamma'], 'S-Gamut3.Cine/S-Log3')
        self.assertEqual(v['lens_attributes'], 'FE 24-105mm F4 G OSS')
        self.assertEqual(v['iris_fnumber'], 4.0)

    def test_it_does_not_read_the_whole_file(self):
        f, _ = self.build()
        mxf.find_acquisition(f, duration_s=5.0)
        self.assertLess(f.bytes_read, f.size,
                        'la scansione non deve diventare una lettura completa')

    def test_an_element_straddling_the_window_edge_is_completed(self):
        """Before, an element that began inside the window and ran past it was
        indistinguishable from no element at all: break, then return None."""
        f, info = self.build()
        edge = info['anc'] + 24          # window ends a few bytes into the element
        self.assertIsNotNone(mxf.find_rtmd(f, info['anc'], edge - info['anc']))

    def test_a_foreign_anc_element_does_not_end_the_search(self):
        """A timecode ANC element sits in the same data track on plenty of cameras."""
        other = fixture.anc_element(b'\x00' * 8, did=0x60, sdid=0x60)
        f, _ = self.build(before_sony=other)
        payload, _at, _tried = mxf.find_acquisition(f, duration_s=5.0)
        self.assertIsNotNone(payload)
        self.assertEqual(self.values(payload)['white_balance_k'], 5600)

    def test_a_later_partition_is_tried_when_the_first_has_nothing(self):
        f, _ = self.build(body_partitions=2)
        payload, _at, _tried = mxf.find_acquisition(f, duration_s=5.0)
        self.assertIsNotNone(payload)

    def test_a_file_with_no_acquisition_metadata_reports_how_hard_it_looked(self):
        f, _ = self.build(payload=b'')
        payload, at, tried = mxf.find_acquisition(f, duration_s=5.0, extra=[1000, 2000])
        self.assertIsNone(payload)
        self.assertIsNone(at)
        self.assertGreater(len(tried), 1, 'deve provare piu di un punto prima di arrendersi')


class TheProfileSurvivesInTheSidecar(unittest.TestCase):
    """Even when the RTMD is genuinely unreachable, the NRT XML carries the capture
    profile - it is a few-KB sidecar, so nothing about the essence layout touches it.
    It was parsed into xml_gamma/xml_primaries and then never used, so an empty
    colour space disabled the node on a clip whose profile we actually knew."""

    def test_the_xml_spelling_maps_to_the_canonical_names(self):
        self.assertEqual(_color_space(None, None, 's-log3-cine', None), 'S-Gamut3.Cine/S-Log3')
        self.assertEqual(_color_space(None, None, 's-log3', 's-gamut3-cine'), 'S-Gamut3.Cine/S-Log3')
        self.assertEqual(_color_space(None, None, 's-log3', 's-gamut3'), 'S-Gamut3/S-Log3')
        self.assertEqual(_color_space(None, None, 's-log2', None), 'S-Gamut/S-Log2')
        self.assertEqual(_color_space(None, None, 's-log', None), 'S-Gamut/S-Log')

    def test_it_only_speaks_when_the_xml_is_clear(self):
        for g in ('rec709', 'hg8009g40', 'hlg', '', None):
            self.assertEqual(_color_space(None, None, g, None), '',
                             'un profilo non log non deve diventare log: %r' % g)

    def test_the_rtmd_still_wins_when_it_is_there(self):
        self.assertEqual(_color_space('S-Gamut3.Cine/S-Log3', None, 's-log2', None),
                         'S-Gamut3.Cine/S-Log3')

    def test_the_node_accepts_a_profile_that_came_from_the_xml(self):
        got = camera.camera_space({'color_space': _color_space(None, None, 's-log3-cine', None)})
        self.assertEqual(got, ('S-Gamut3.Cine', 'SLog3'))

    def test_an_s_log_in_the_xml_is_full_scale(self):
        """The exact-match set did not contain 's-log3-cine', so an S-Log3 clip was
        classified as VIDEO - backwards for a curve this module lists as full scale."""
        self.assertEqual(gamma_scale(None, 's-log3-cine'), FULL)
        self.assertEqual(gamma_scale(None, 'S-Log3-Cine'), FULL)
        self.assertEqual(gamma_scale(None, 'slog3'), FULL)
        self.assertEqual(gamma_scale(None, 'rec709'), VIDEO)
        self.assertIsNone(gamma_scale(None, None))


class TheRecordSaysWhatItKnows(unittest.TestCase):
    def record(self, **meta):
        base = {'container': 'MXF', 'color_space': '', 'model': 'ILME-FX6V'}
        base.update(meta)
        return plugin_cache.build_record({'path': '/x/clip.mxf', 'meta': base,
                                          'display': {}, 'changes': {}})

    def test_a_clip_known_only_from_its_xml_still_develops(self):
        rec = self.record(color_space='S-Gamut3.Cine/S-Log3', color_space_from='xml')
        self.assertEqual(rec['supported'], 1)
        self.assertEqual(rec['rtmd_found'], 0)
        self.assertEqual(rec['color_space_from'], 'xml')

    def test_missing_shooting_values_are_not_dressed_up_as_a_measurement(self):
        """'5600K stimato' reads like a reading. It must not appear when the
        per-frame metadata was never found."""
        rec = self.record(color_space='S-Gamut3.Cine/S-Log3')
        self.assertNotIn('5600K', rec['white_balance'])
        self.assertIn('non disponibili', rec['white_balance'])

    def test_a_clip_with_metadata_reports_them_normally(self):
        rec = plugin_cache.build_record({
            'path': '/x/clip.mxf', 'display': {}, 'changes': {},
            'rtmd': [{'key': 'white_balance_k', 'value': 5600, 'display': '5600 K'}],
            'meta': {'container': 'MXF', 'color_space': 'S-Gamut3.Cine/S-Log3',
                     'white_balance_k': 5600, 'tint': 15.17, 'exposure_index': 800}})
        self.assertEqual(rec['rtmd_found'], 1)
        self.assertEqual(rec['color_space_from'], 'rtmd')
        self.assertIn('5600K', rec['white_balance'])
        self.assertIn('Tint 15.17', rec['white_balance'])


class ThePluginSideGuards(unittest.TestCase):
    """Source-level, because the plugin cannot be exercised off macOS."""

    def setUp(self):
        with open(os.path.join(ROOT, 'ofx', 'SLogMetaRaw', 'SLogMetaRaw.cpp'),
                  encoding='utf-8') as fh:
            self.src = fh.read()

    def test_the_read_budget_escalates(self):
        """Short first, so the UI thread is not held for a clip that reads fast;
        longer only after a timeout, for a long take on an external drive."""
        self.assertIn('kReadBudgetSec[] = { 2, 8, 20 }', self.src)

    def test_a_clean_failure_is_not_retried(self):
        """A file that is not Sony answers immediately. Retrying it three times
        would freeze the panel for half a minute to reach the same answer."""
        body = self.src[self.src.index('static bool runExtractor('):
                        self.src.index('// "Rileggi metadata" pressed on the node')]
        self.assertIn('return false;     // it answered', body)

    def test_the_panel_says_when_the_shooting_values_are_missing(self):
        self.assertIn('meta.rtmdFound', self.src)
        self.assertIn("profilo dedotto dall'XML della clip", self.src)

    def test_an_older_cache_record_keeps_its_meaning(self):
        """rtmd_found did not exist before this fix; records without it were all
        written from metadata that had been found."""
        self.assertIn('j.count("rtmd_found") ? atoi(j["rtmd_found"].c_str()) != 0 : true',
                      self.src)


if __name__ == '__main__':
    unittest.main()
