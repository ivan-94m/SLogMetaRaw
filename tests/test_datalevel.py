# SPDX-License-Identifier: GPL-3.0-or-later
"""Data level: which scale a clip is on, and the correction the node applies.

The numbers the assertions use are Sony's published ones (Technical Summary for
S-Gamut3.Cine/S-Log3 and S-Gamut3/S-Log3): S-Log3 black at 10-bit code 95, 18%
grey at 420, 90% white at 598; S-Log2 and S-Log black at 90.
"""
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tests'))

import develop_model as dm                                    # noqa: E402
from slogmetaraw import datalevel as dl, mxf, plugin_cache, resolve_io   # noqa: E402

V2F = dl.remap(dl.VIDEO, dl.FULL)
F2V = dl.remap(dl.FULL, dl.VIDEO)
SLOG3, SLOG2 = 9, 8
SG3C, SG3, SGAMUT, DWG = 8, 7, 6, 0


class FakeClip:
    """The bits of MediaPoolItem this code touches."""

    def __init__(self, level='Auto', writable=True):
        self.level = level
        self.writable = writable
        self.sets = []

    def GetClipProperty(self, name=None):
        return self.level if name == 'Data Level' else ''

    def SetClipProperty(self, name, value):
        self.sets.append((name, value))
        if not self.writable:
            return False
        if name == 'Data Level':
            self.level = value
        return True


class Remap(unittest.TestCase):
    def test_video_to_full_is_the_legal_window(self):
        gain, offset = V2F
        self.assertAlmostEqual(gain, 876 / 1023)
        self.assertAlmostEqual(offset, 64 / 1023)
        # 0.0 and 1.0 on the video scale are code 64 and code 940
        self.assertAlmostEqual(0.0 * gain + offset, 64 / 1023)
        self.assertAlmostEqual(1.0 * gain + offset, 940 / 1023)

    def test_the_two_directions_are_exact_inverses(self):
        for x in (0.0, 0.0625, 0.41, 0.92, 1.0, -0.2, 1.4):
            back = (x * V2F[0] + V2F[1]) * F2V[0] + F2V[1]
            self.assertAlmostEqual(back, x, places=12)

    def test_same_scale_is_the_identity(self):
        self.assertEqual(dl.remap(dl.FULL, dl.FULL), (1.0, 0.0))
        self.assertEqual(dl.remap(dl.VIDEO, dl.VIDEO), (1.0, 0.0))
        self.assertEqual(dl.remap(None, dl.FULL), (1.0, 0.0))


class RequiredLevel(unittest.TestCase):
    def test_sony_log_curves_need_the_full_scale(self):
        for gamma in ('S-Log', 'S-Log2', 'S-Gamut3/S-Log3', 'S-Gamut3.Cine/S-Log3'):
            self.assertEqual(dl.required_level({'capture_gamma': gamma})[0], dl.FULL, gamma)

    def test_broadcast_curves_need_the_video_scale(self):
        for gamma in ('ITU-R BT.709-5', 'Cine1', 'Cine2', 'Cine4', 'S-Cinetone',
                      'ITU-R BT.2100 HLG', 'HG4609G33', 'R709 800%', 'Standard'):
            self.assertEqual(dl.required_level({'capture_gamma': gamma})[0], dl.VIDEO, gamma)

    def test_super_white_ceiling_is_named_in_the_reason(self):
        self.assertIn('109%', dl.required_level({'capture_gamma': 'Cine1'})[1])
        self.assertIn('100%', dl.required_level({'capture_gamma': 'Cine2'})[1])

    def test_falls_back_to_the_nrt_xml_gamma(self):
        self.assertEqual(dl.required_level({'xml_gamma': 's-log3'})[0], dl.FULL)
        self.assertEqual(dl.required_level({'xml_gamma': 'rec709'})[0], dl.VIDEO)

    def test_unknown_gamma_gives_no_answer(self):
        self.assertEqual(dl.required_level({})[0], None)


class DeclaredLevel(unittest.TestCase):
    def test_sony_acquisition_metadata_wins(self):
        m = {'luminance_code_range': 'Full Scaled Code', 'v_full_range': False, 'container': 'MP4'}
        level, source = dl.declared_level(m)
        self.assertEqual(level, dl.FULL)
        self.assertIn('0x8120', source)

    def test_vui_flag_is_used_when_there_is_no_sony_metadata(self):
        self.assertEqual(dl.declared_level({'v_full_range': True, 'container': 'MP4'})[0], dl.FULL)
        self.assertEqual(dl.declared_level({'v_full_range': False, 'container': 'MP4'})[0], dl.VIDEO)

    def test_colr_box_is_only_a_fallback_for_a_missing_vui(self):
        # regression: dict.get(k, default) returned the stored None and skipped the
        # fallback, so a file with no VUI but a colr box was reported as undeclared
        m = {'v_full_range': None, 'v_colr_full_range': True, 'container': 'MP4'}
        self.assertEqual(dl.declared_level(m)[0], dl.FULL)
        # an explicit "video range" VUI must NOT be overridden by the colr box
        m = {'v_full_range': False, 'v_colr_full_range': True, 'container': 'MP4'}
        self.assertEqual(dl.declared_level(m)[0], dl.VIDEO)

    def test_an_mxf_never_trusts_the_scanned_sps(self):
        m = {'v_full_range': True, 'container': 'MXF'}
        self.assertEqual(dl.declared_level(m)[0], None)

    def test_mxf_reference_levels_decide_for_an_mxf(self):
        video = {'container': 'MXF', 'mxf_component_depth': 10, 'mxf_black_ref': 64,
                 'mxf_white_ref': 940, 'mxf_color_range': 897}
        full = {'container': 'MXF', 'mxf_component_depth': 10, 'mxf_black_ref': 0,
                'mxf_white_ref': 1023, 'mxf_color_range': 1024}
        self.assertEqual(dl.declared_level(video)[0], dl.VIDEO)
        self.assertEqual(dl.declared_level(full)[0], dl.FULL)

    def test_nothing_declared_is_reported_as_nothing(self):
        self.assertEqual(dl.declared_level({'container': 'MP4'})[0], None)


class MxfPictureDescriptor(unittest.TestCase):
    class File:
        def __init__(self, data):
            self.data, self.size = data, len(data)

        def read_at(self, pos, n):
            return self.data[pos:pos + n]

    def wrap(self, local_set, key=None):
        body = bytes([0x83]) + len(local_set).to_bytes(3, 'big') + local_set
        return b'\x00' * 64 + (key or mxf.CDCI_KEY) + body + b'\x00' * 32

    def test_reads_the_reference_levels(self):
        ls = bytes.fromhex('330100040000000A' '3304000400000040'
                           '33050004000003AC' '3306000400000381')
        got = mxf.find_picture_levels(self.File(self.wrap(ls)))
        self.assertEqual(got, {'mxf_component_depth': 10, 'mxf_black_ref': 64,
                               'mxf_white_ref': 940, 'mxf_color_range': 897})

    def test_reads_an_rgba_descriptor_too(self):
        ls = bytes.fromhex('330100040000000A' '3304000400000000' '33050004000003FF')
        got = mxf.find_picture_levels(self.File(self.wrap(ls, mxf.RGBA_KEY)))
        self.assertEqual(got['mxf_black_ref'], 0)

    def test_a_descriptor_without_levels_is_ignored(self):
        ls = bytes.fromhex('330100040000000A' '3302000400000002')
        self.assertEqual(mxf.find_picture_levels(self.File(self.wrap(ls))), {})

    def test_no_descriptor_at_all(self):
        self.assertEqual(mxf.find_picture_levels(self.File(b'\x00' * 400)), {})

    def test_reads_only_the_head_of_the_file(self):
        f = self.File(b'\x00' * 400)
        with mock.patch.object(self.File, 'read_at', autospec=True,
                               side_effect=lambda s, p, n: s.data[p:p + n]) as read:
            mxf.find_picture_levels(f)
        self.assertEqual([c.args[1] for c in read.call_args_list], [0])


class Decide(unittest.TestCase):
    SLOG3 = {'capture_gamma': 'S-Gamut3.Cine/S-Log3', 'container': 'MP4',
             'luminance_code_range': 'Full Scaled Code'}

    def test_resolve_on_video_for_a_log_clip_is_corrected(self):
        d = dl.decide(self.SLOG3, dl.VIDEO)
        self.assertEqual(d['fix'], 1)
        self.assertAlmostEqual(d['gain'], V2F[0])
        self.assertAlmostEqual(d['offset'], V2F[1])

    def test_resolve_already_on_full_needs_nothing(self):
        d = dl.decide(self.SLOG3, dl.FULL)
        self.assertEqual((d['fix'], d['gain'], d['offset']), (0, 1.0, 0.0))

    def test_auto_never_corrects_and_says_what_to_do(self):
        d = dl.decide(self.SLOG3, dl.AUTO)
        self.assertEqual(d['fix'], 0)
        self.assertFalse(d['known'])
        self.assertIn('Attributi clip', d['note'])

    def test_a_missing_attribute_behaves_like_auto(self):
        self.assertEqual(dl.decide(self.SLOG3, None)['fix'], 0)

    def test_a_rec709_clip_read_as_full_is_corrected_the_other_way(self):
        d = dl.decide({'capture_gamma': 'ITU-R BT.709-5', 'container': 'MP4'}, dl.FULL)
        self.assertEqual(d['fix'], 1)
        self.assertAlmostEqual(d['gain'], F2V[0])

    def test_unknown_gamma_never_corrects(self):
        self.assertEqual(dl.decide({'container': 'MP4'}, dl.VIDEO)['fix'], 0)

    def test_a_flag_that_contradicts_the_gamma_is_reported_not_obeyed(self):
        # Sony writes the range flag inconsistently on the consumer bodies; the
        # published curve is the authority, but the disagreement has to be visible
        m = {'capture_gamma': 'S-Log2', 'v_full_range': False, 'container': 'MP4'}
        d = dl.decide(m, dl.VIDEO)
        self.assertEqual(d['required'], dl.FULL)
        self.assertEqual(d['declared'], dl.VIDEO)
        self.assertIn('conflict', d)
        self.assertEqual(d['fix'], 1)

    def test_override_forces_the_target_scale(self):
        d = dl.decide({'container': 'MP4'}, dl.VIDEO, override_required=dl.FULL)
        self.assertEqual(d['fix'], 1)


class ResolveAttribute(unittest.TestCase):
    def record(self, gamma='S-Gamut3.Cine/S-Log3'):
        return {'path': '/x.MP4', 'display': {}, 'changes': {},
                'meta': {'capture_gamma': gamma, 'container': 'MP4', 'level_required': dl.FULL
                         if gamma.endswith('S-Log3') else dl.VIDEO}}

    def test_reads_the_three_values(self):
        for text, want in (('Auto', dl.AUTO), ('Full', dl.FULL), ('Video', dl.VIDEO),
                           ('full', dl.FULL), ('', None), ('Nonsense', None)):
            self.assertEqual(resolve_io.read_data_level(FakeClip(text)), want, text)

    def test_a_clip_that_cannot_answer_gives_none(self):
        clip = mock.Mock()
        clip.GetClipProperty.side_effect = RuntimeError('boom')
        self.assertIsNone(resolve_io.read_data_level(clip))

    def test_sets_the_attribute_when_asked(self):
        clip, r = FakeClip('Auto'), self.record()
        report = resolve_io.sync_data_level(clip, r, apply_fix=True)
        self.assertEqual(report['set'], dl.FULL)
        self.assertEqual(clip.sets, [('Data Level', 'Full')])
        # and the decision is then recomputed against the value we just wrote
        self.assertEqual(r['meta']['resolve_data_level'], dl.FULL)
        self.assertEqual(r['data_level']['fix'], 0)

    def test_leaves_the_attribute_alone_when_not_asked(self):
        clip, r = FakeClip('Video'), self.record()
        report = resolve_io.sync_data_level(clip, r, apply_fix=False)
        self.assertIsNone(report['set'])
        self.assertEqual(clip.sets, [])
        # the node is told to correct it instead
        self.assertEqual(r['data_level']['fix'], 1)

    def test_an_already_correct_attribute_is_not_rewritten(self):
        clip, r = FakeClip('Full'), self.record()
        resolve_io.sync_data_level(clip, r, apply_fix=True)
        self.assertEqual(clip.sets, [])

    def test_a_refused_write_is_reported_and_not_believed(self):
        clip, r = FakeClip('Video', writable=False), self.record()
        report = resolve_io.sync_data_level(clip, r, apply_fix=True)
        self.assertEqual(report['set'], 'FAILED Full')
        self.assertEqual(r['meta']['resolve_data_level'], dl.VIDEO)
        self.assertEqual(r['data_level']['fix'], 1)   # so the node still corrects it


class CacheRecord(unittest.TestCase):
    def record(self, host, gamma='S-Gamut3.Cine/S-Log3', space='S-Gamut3.Cine/S-Log3'):
        r = {'path': '/x.MP4', 'display': {}, 'changes': {},
             'meta': {'model': 'ILME-FX30', 'capture_gamma': gamma, 'color_space': space,
                      'container': 'MP4', 'iso': 800, 'resolve_data_level': host,
                      'luminance_code_range': 'Full Scaled Code'}}
        return plugin_cache.build_record(r)

    def test_version_was_bumped_for_the_new_fields(self):
        self.assertGreaterEqual(plugin_cache.VERSION, 3)

    def test_the_plugin_gets_codes_not_words(self):
        rec = self.record(dl.VIDEO)
        self.assertEqual(rec['level_required'], 1)   # Full
        self.assertEqual(rec['level_host'], 0)       # Video
        self.assertEqual(rec['level_fix'], 1)
        self.assertAlmostEqual(rec['level_gain'], V2F[0])
        self.assertAlmostEqual(rec['level_offset'], V2F[1])

    def test_auto_is_minus_one_so_the_node_does_not_guess(self):
        rec = self.record(dl.AUTO)
        self.assertEqual(rec['level_host'], -1)
        self.assertEqual(rec['level_fix'], 0)

    def test_a_non_log_clip_asks_for_the_video_scale(self):
        rec = self.record(dl.FULL, gamma='ITU-R BT.709-5', space='Rec.709')
        self.assertEqual(rec['level_required'], 0)
        self.assertEqual(rec['level_host'], 1)
        self.assertEqual(rec['level_fix'], 1)

    def test_every_key_the_plugin_reads_is_present(self):
        rec = self.record(dl.VIDEO)
        for key in ('level_required', 'level_host', 'level_gain', 'level_offset',
                    'level_fix', 'level_note', 'data_level'):
            self.assertIn(key, rec)


class CorrectionIsExact(unittest.TestCase):
    """The point of the whole feature: after the fix the log decode lands on the
    published Sony values, and it lands on the same place whatever colour space
    Resolve hands the node."""

    def host_value(self, code, scale):
        """What Resolve gives the node for a 10-bit code value at that Data Level."""
        return code / 1023.0 if scale == dl.FULL else (code - 64.0) / 876.0

    def fixed_linear(self, code, node_space, node_gamma, cam_space, cam_gamma, host=dl.VIDEO):
        """Linear light in the camera gamut, as the node computes it."""
        x = self.host_value(code, host)
        # what Resolve did before the node: decode, and (RCM) convert to the timeline
        lin_cam = dm.decode1(x, cam_gamma)
        if (node_space, node_gamma) != (cam_space, cam_gamma):
            lin_node = dm.mul(dm.MATS[node_space][1], dm.mul(dm.MATS[cam_space][0], [lin_cam] * 3))
            entering = [dm.encode1(c, node_gamma) for c in lin_node]
        else:
            entering = [x] * 3
        # the node: decode with the node's own curve, then the data level stage
        lin = [dm.decode1(c, node_gamma) for c in entering]
        gain, offset = dl.remap(host, dl.FULL)
        lin = dm.fix_levels(lin, node_space, cam_space, cam_gamma, gain, offset)
        return dm.mul(dm.MATS[cam_space][1], dm.mul(dm.MATS[node_space][0], lin))

    def test_the_fix_recovers_the_full_scale_reading_exactly(self):
        """Whatever Resolve did, after the correction the node decodes the clip's code
        values exactly as if Resolve had been on Full all along. This is the claim the
        whole feature rests on, so it is asserted to the last float digit."""
        for gamma, space in ((SLOG3, SG3C), (SLOG3, SG3), (SLOG2, SGAMUT), (7, SGAMUT)):
            for code in (0, 64, 90, 95, 200, 420, 598, 870, 940, 1023):
                got = self.fixed_linear(code, space, gamma, space, gamma)[1]
                self.assertAlmostEqual(got, dm.decode1(code / 1023.0, gamma), places=9,
                                       msg='gamma %d, code %d' % (gamma, code))

    def test_sonys_published_code_values_are_where_the_curves_put_them(self):
        """Sony's own table against these transfer functions, on the full scale:
        black / 18% grey / 90% white. Sony rounds to whole code values, so the
        tolerance is one 10-bit code."""
        for gamma, table in ((SLOG3, ((0.0, 95), (0.18, 420), (0.9, 598))),
                             (SLOG2, ((0.0, 90), (0.18, 347), (0.9, 582))),
                             (7, ((0.0, 90), (0.18, 394), (0.9, 636)))):
            for linear, code in table:
                exact = dm.encode1(linear, gamma) * 1023.0
                self.assertLess(abs(exact - code), 1.0,
                                'gamma %d: %g linear -> code %.2f, Sony publishes %d'
                                % (gamma, linear, exact, code))

    def test_without_the_fix_slog3_black_goes_negative(self):
        # the failure this feature exists to remove: code 95 read on the video scale
        wrong = dm.decode1(self.host_value(95, dl.VIDEO), SLOG3)
        self.assertLess(wrong, -0.008)

    def test_the_same_result_through_dwg_intermediate_and_aces(self):
        """A colour-managed timeline runs Resolve's input transform before the node,
        so the image arrives as DaVinci Intermediate or ACEScct, not as S-Log3. The
        round-trip inside the correction has to give the identical answer."""
        for code in (95, 200, 420, 598, 870):
            direct = self.fixed_linear(code, SG3C, SLOG3, SG3C, SLOG3)
            for node_space, node_gamma in ((DWG, 0), (10, 10), (1, 5), (DWG, 1)):
                through = self.fixed_linear(code, node_space, node_gamma, SG3C, SLOG3)
                for a, b in zip(direct, through):
                    self.assertAlmostEqual(a, b, places=6,
                                           msg='code %d through space %d gamma %d'
                                               % (code, node_space, node_gamma))

    def test_a_full_range_clip_read_as_full_is_left_alone(self):
        for code in (95, 420, 598):
            x = self.host_value(code, dl.FULL)
            lin = [dm.decode1(x, SLOG3)] * 3
            gain, offset = dl.remap(dl.FULL, dl.FULL)
            same = dm.fix_levels(lin, SG3C, SG3C, SLOG3, gain, offset)
            for a, b in zip(lin, same):
                self.assertAlmostEqual(a, b, places=9)

    def test_the_stage_is_reversible(self):
        """Applying video->full and then full->video returns the original pixel, so
        the node never destroys information - it only re-anchors it."""
        for x in (0.02, 0.09, 0.41, 0.94, 1.1):
            lin = [dm.decode1(x, SLOG3)] * 3
            there = dm.fix_levels(lin, SG3C, SG3C, SLOG3, *V2F)
            back = dm.fix_levels(there, SG3C, SG3C, SLOG3, *F2V)
            for a, b in zip(lin, back):
                self.assertAlmostEqual(a, b, places=9)


class Normalise(unittest.TestCase):
    """extract._normalise is where the raw parser output becomes the data level
    decision, and where the codec flags are given their precedence."""

    def run_one(self, container, meta):
        from slogmetaraw.extract import _normalise
        out = {'path': '/x', 'container': container, 'meta': dict(meta), 'display': {},
               'rtmd': [], 'changes': {}, 'warnings': []}
        _normalise(out)
        return out

    def test_an_slog3_mp4_flagged_full_asks_for_full(self):
        out = self.run_one('MP4', {'capture_gamma': 'S-Gamut3.Cine/S-Log3',
                                   'color_primaries': 'S-Gamut3.Cine', 'v_full_range': True})
        self.assertEqual(out['meta']['file_range'], 'Full')
        self.assertEqual(out['meta']['level_required'], dl.FULL)
        self.assertEqual(out['meta']['level_declared'], dl.FULL)
        self.assertIn('Auto', out['meta']['data_level'])   # Resolve not asked yet
        self.assertEqual(out['data_level']['fix'], 0)

    def test_a_missing_vui_falls_through_to_the_colr_box(self):
        out = self.run_one('MP4', {'capture_gamma': 'S-Log2', 'v_full_range': None,
                                   'v_colr_full_range': True})
        self.assertEqual(out['meta']['file_range'], 'Full')

    def test_an_explicit_video_vui_is_not_overridden_by_colr(self):
        out = self.run_one('MP4', {'capture_gamma': 'ITU-R BT.709-5', 'v_full_range': False,
                                   'v_colr_full_range': True})
        self.assertEqual(out['meta']['file_range'], 'Video (legal)')

    def test_an_mxf_uses_its_descriptor_and_ignores_the_scanned_sps(self):
        out = self.run_one('MXF', {'capture_gamma': 'S-Gamut3.Cine/S-Log3', 'v_full_range': True,
                                   'mxf_black_ref': 0, 'mxf_white_ref': 1023,
                                   'mxf_color_range': 1024, 'mxf_component_depth': 10})
        self.assertIsNone(out['meta']['file_range'])       # the SPS scan is not trusted
        self.assertEqual(out['meta']['level_declared'], dl.FULL)

    def test_a_flag_that_contradicts_the_curve_becomes_a_warning(self):
        out = self.run_one('MP4', {'capture_gamma': 'S-Gamut3.Cine/S-Log3', 'v_full_range': False})
        self.assertEqual(out['meta']['level_required'], dl.FULL)
        self.assertTrue(any('Data level' in w for w in out['warnings']))


class ReportRows(unittest.TestCase):
    """The Catalyst-style panel drops a row whose value is None or '': an expression
    that yields False instead leaves a literal "False" on screen."""

    def sections(self, meta):
        from slogmetaraw.extract import _sections
        out = {'path': '/x.MXF', 'meta': meta, 'display': {}, 'rtmd': [], 'changes': {}}
        return {label: value for _title, rows in _sections(out) for label, value in rows}

    def test_no_row_is_ever_a_bare_boolean(self):
        for meta in ({}, {'capture_gamma': 'S-Log2'},
                     {'mxf_black_ref': 64, 'mxf_white_ref': 940, 'mxf_component_depth': 10}):
            for label, value in self.sections(meta).items():
                self.assertNotIsInstance(value, bool, '%s = %r' % (label, value))

    def test_the_mxf_levels_row_appears_only_when_they_were_read(self):
        self.assertNotIn('Livelli di riferimento MXF', self.sections({}))
        rows = self.sections({'mxf_black_ref': 0, 'mxf_white_ref': 1023,
                              'mxf_color_range': 1024, 'mxf_component_depth': 10})
        self.assertIn('nero 0, bianco 1023', rows['Livelli di riferimento MXF'])


if __name__ == '__main__':
    unittest.main()
