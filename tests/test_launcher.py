# SPDX-License-Identifier: GPL-3.0-or-later
"""Regression tests for Resolve's menu entry, without requiring a running host."""
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('slogmetaraw_launcher', ROOT / 'resolve_script' / 'SLogMetaRaw.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class Launcher(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.log = Path(self.temp.name) / 'logs' / 'launcher.log'
        log_patch = patch.object(launcher, 'LOG_PATH', str(self.log))
        log_patch.start()
        self.addCleanup(log_patch.stop)

    def test_injected_connection_does_not_require_external_scripting(self):
        resolve = object()
        bmd = Mock()
        self.assertIs(launcher._connect({'resolve': resolve}, bmd), resolve)
        bmd.scriptapp.assert_not_called()

    def test_injected_fusion_recovers_missing_resolve_connection(self):
        resolve = object()
        for alias in ('fusion', 'fu', 'app'):
            with self.subTest(alias=alias):
                fusion = types.SimpleNamespace(GetResolve=lambda: resolve)
                bmd = Mock()
                self.assertIs(launcher._connect({alias: fusion}, bmd), resolve)
                bmd.scriptapp.assert_not_called()

    def test_broken_injected_route_does_not_prevent_external_fallback(self):
        resolve = object()
        fusion = Mock()
        fusion.GetResolve.side_effect = RuntimeError('stale connection')
        bmd = Mock()
        bmd.scriptapp.return_value = resolve
        self.assertIs(launcher._connect({'fusion': fusion}, bmd), resolve)

    def test_fusion_scriptapp_recovers_missing_resolve_scriptapp(self):
        resolve = object()
        fusion = types.SimpleNamespace(GetResolve=lambda: resolve)
        bmd = Mock()
        bmd.scriptapp.side_effect = [None, fusion]
        self.assertIs(launcher._connect({}, bmd), resolve)

    def test_menu_connects_when_resolve_is_bound_to_local_interface_only(self):
        resolve = object()
        bmd = Mock()
        bmd.scriptapp.side_effect = lambda name, *args: (
            resolve if name == 'Resolve' and args == ('192.168.1.11', 1.0) else None)
        with patch.object(launcher, '_local_ipv4_addresses', return_value=['192.168.1.11']):
            self.assertIs(launcher._connect({'bmd': bmd}, bmd), resolve)
        self.assertEqual(bmd.scriptapp.call_args_list[0].args, ('Resolve',))
        bmd.pinghosts.assert_not_called()
        self.assertIn('indirizzo locale 192.168.1.11', self.log.read_text())

    def test_interface_fallback_uses_only_assigned_local_addresses(self):
        output = '''lo0: flags=8049<UP,LOOPBACK,RUNNING>
    inet 127.0.0.1 netmask 0xff000000
    inet6 ::1 prefixlen 128
en0: flags=8863<UP,BROADCAST,RUNNING>
    inet 192.168.1.11 netmask 0xffffff00 broadcast 192.168.1.255
en1: flags=8863<UP,BROADCAST,RUNNING>
    inet 10.0.0.3 netmask 0xffffff00 broadcast 10.0.0.255
    inet 192.168.1.11 netmask 0xffffff00
    inet 0.0.0.0 netmask 0xffffff00
    inet invalid-address netmask 0xffffff00
'''
        with patch.object(launcher.subprocess, 'run', return_value=types.SimpleNamespace(stdout=output)) as run:
            self.assertEqual(launcher._local_ipv4_addresses(), ['192.168.1.11', '10.0.0.3'])
        self.assertEqual(run.call_args.args[0], ['/sbin/ifconfig', '-a'])

    def test_interface_inventory_failure_does_not_mask_connection_error(self):
        with patch.object(launcher.subprocess, 'run', side_effect=OSError('unavailable')):
            self.assertEqual(launcher._local_ipv4_addresses(), [])

    def test_retry_waits_for_connection_and_rejects_false(self):
        connected = object()
        obtain = Mock(side_effect=[False, None, connected])
        with patch.object(launcher.time, 'sleep') as sleep:
            self.assertIs(launcher._retry(obtain, 'unavailable', attempts=3), connected)
        self.assertEqual(sleep.call_count, 2)

    def test_retry_preserves_underlying_error(self):
        cause = RuntimeError('RPC unavailable')
        with self.assertRaisesRegex(RuntimeError, 'connection unavailable') as result:
            launcher._retry(Mock(side_effect=cause), 'connection unavailable', attempts=1)
        self.assertIs(result.exception.__cause__, cause)

    def test_startup_error_reports_traceback_instead_of_disappearing(self):
        resolve = Mock()
        fusion = types.SimpleNamespace(UIManager=object())
        namespace = {'resolve': resolve, 'fusion': fusion, 'bmd': Mock()}
        with patch.object(launcher, '_load_ui', side_effect=ImportError('missing parser')):
            with patch.object(launcher.subprocess, 'run') as dialog:
                with patch.object(launcher.sys, 'stderr', io.StringIO()):
                    self.assertFalse(launcher.main(namespace))
        self.assertIn('ImportError: missing parser', self.log.read_text())
        self.assertIn('missing parser', dialog.call_args.args[0][-1])
        self.assertIn(str(self.log), dialog.call_args.args[0][-1])

    def test_successful_menu_launch_passes_host_objects_to_ui(self):
        resolve = Mock()
        fusion = types.SimpleNamespace(UIManager=object())
        bmd = Mock()
        ui = Mock()
        with patch.object(launcher, '_load_ui', return_value=ui):
            self.assertTrue(launcher.main({'resolve': resolve, 'fusion': fusion, 'bmd': bmd}))
        ui.main.assert_called_once_with(resolve, fusion, bmd)

    def test_missing_library_identifies_installation_path(self):
        missing = os.path.join(self.temp.name, "libreria d'Ivan")
        with patch.object(launcher, 'LIB_DIR', missing):
            with self.assertRaises(RuntimeError) as result:
                launcher._load_ui()
        self.assertIn(missing, str(result.exception))

    def test_error_dialog_passes_unicode_and_quotes_as_data(self):
        message = 'Libreria d\'Ivan: "è mancante"'
        with patch.object(launcher.subprocess, 'run') as dialog:
            with patch.object(launcher.sys, 'stderr', io.StringIO()):
                launcher._report_error(message, 'traceback')
        args = dialog.call_args.args[0]
        self.assertNotIn(message, args[2])
        self.assertIn(message, args[3])

    def test_unwritable_log_does_not_prevent_startup(self):
        with patch('builtins.open', side_effect=PermissionError('read only')):
            launcher._log('diagnostic')


if __name__ == '__main__':
    unittest.main()
