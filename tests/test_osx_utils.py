# SPDX-License-Identifier: GPL-3.0-or-later
"""Smoke checks for slogmetaraw/osx_utils.py (macOS only)."""
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from slogmetaraw import osx_utils  # noqa: E402


class OsxUtils(unittest.TestCase):
    def test_display_bounds(self):
        b = osx_utils.display_bounds()
        if b is None:
            self.skipTest('No display accessible in this session')
        self.assertEqual(len(b), 4)
        self.assertGreater(b[2], 0)
        self.assertGreater(b[3], 0)

    def test_headless_display_uses_fallback(self):
        cg = mock.Mock()
        cg.CGDisplayBounds.return_value = osx_utils._CGRect(
            osx_utils._CGPoint(0, 0), osx_utils._CGSize(0, 0))
        with mock.patch.object(osx_utils, '_coregraphics', return_value=cg):
            self.assertIsNone(osx_utils.display_bounds())

    def test_window_lookup_failure_does_not_break_startup(self):
        cg = mock.Mock()
        cg.CGWindowListCopyWindowInfo.return_value = 123
        cg.CFArrayGetCount.side_effect = RuntimeError('window server unavailable')
        with mock.patch.object(osx_utils, '_coregraphics', return_value=cg):
            with mock.patch.object(osx_utils, '_cfstring', side_effect=range(1, 7)):
                self.assertIsNone(osx_utils.resolve_window_bounds())
        self.assertEqual(cg.CFRelease.call_count, 7)

    def test_missing_window_values_never_reach_core_foundation(self):
        # Calling CFNumberGetValue(NULL) can terminate the interpreter; Python
        # exception handlers cannot catch a native segmentation fault.
        with mock.patch.object(osx_utils, '_coregraphics') as graphics:
            self.assertEqual(osx_utils._cfnumber_double(None), 0)
            self.assertEqual(osx_utils._cfstring_value(None), '')
        graphics.assert_not_called()

    def test_resolve_window_bounds_shape(self):
        # None when Resolve is not running; if it is, expect a sane rectangle
        b = osx_utils.resolve_window_bounds()
        if b is not None:
            self.assertEqual(len(b), 4)
            self.assertGreater(b[2], 0)
            self.assertGreater(b[3], 0)

    def test_play_sound_never_raises(self):
        with mock.patch('slogmetaraw.osx_utils.subprocess.Popen') as popen:
            osx_utils.play_sound(True)
            osx_utils.play_sound(False)
            self.assertEqual(popen.call_count, 2)


if __name__ == '__main__':
    unittest.main()
