# SPDX-License-Identifier: GPL-3.0-or-later
"""Connection and single-clip write used by the plugin's --to-resolve child."""
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from slogmetaraw import connect


class LocalAddresses(unittest.TestCase):
    def test_parses_ifconfig_and_filters_loopback(self):
        output = ('lo0: flags=8049<UP,LOOPBACK,RUNNING> mtu 16384\n'
                  '\tinet 127.0.0.1 netmask 0xff000000\n'
                  'en0: flags=8863<UP,BROADCAST> mtu 1500\n'
                  '\tinet 192.168.1.11 netmask 0xffffff00 broadcast 192.168.1.255\n'
                  '\tinet6 fe80::1%en0 prefixlen 64\n'
                  'utun3: flags=8051<UP,POINTOPOINT> mtu 1380\n'
                  '\tinet 0.0.0.0 --> 0.0.0.0\n'
                  '\tinet 10.9.0.5 --> 10.9.0.5 netmask 0xffffffff\n'
                  '\tinet 192.168.1.11 netmask 0xffffff00\n')
        with mock.patch('subprocess.run', return_value=mock.Mock(stdout=output, returncode=0)):
            self.assertEqual(connect._local_ipv4_addresses(), ['192.168.1.11', '10.9.0.5'])

    def test_ifconfig_failure_gives_no_addresses(self):
        with mock.patch('subprocess.run', side_effect=OSError('no ifconfig')):
            self.assertEqual(connect._local_ipv4_addresses(), [])


class Connect(unittest.TestCase):
    def fake_bmd(self, results):
        module = mock.Mock()
        calls = []

        def scriptapp(*args):
            calls.append(args)
            return results.pop(0) if results else None

        module.scriptapp = scriptapp
        return module, calls

    def test_localhost_connection_wins(self):
        resolve = object()
        bmd, _ = self.fake_bmd([resolve])
        with mock.patch.dict(sys.modules, {'DaVinciResolveScript': bmd}):
            self.assertIs(connect.connect(), resolve)

    def test_falls_back_to_local_ipv4_addresses(self):
        resolve = object()
        bmd, calls = self.fake_bmd([None, resolve])
        with mock.patch.dict(sys.modules, {'DaVinciResolveScript': bmd}):
            with mock.patch.object(connect, '_local_ipv4_addresses', return_value=['192.168.1.11', '10.9.0.5']):
                self.assertIs(connect.connect(), resolve)
        self.assertEqual(calls, [('Resolve',), ('Resolve', '192.168.1.11', 1.0)])

    def test_connection_failure_raises(self):
        bmd, _ = self.fake_bmd([None, None])
        with mock.patch.dict(sys.modules, {'DaVinciResolveScript': bmd}):
            with mock.patch.object(connect, '_local_ipv4_addresses', return_value=['192.168.1.11']):
                with self.assertRaisesRegex(RuntimeError, 'connessione'):
                    connect.connect()

    def test_missing_module_raises(self):
        with mock.patch('builtins.__import__', side_effect=ImportError('no module')):
            with self.assertRaisesRegex(RuntimeError, 'DaVinciResolveScript'):
                connect.connect()


class ApplyPath(unittest.TestCase):
    def make_resolve(self, clip_paths):
        clips = []
        for path in clip_paths:
            clip = mock.Mock()
            clip.GetClipProperty.return_value = path
            clips.append(clip)
        root = mock.Mock()
        root.GetClipList.return_value = clips
        root.GetSubFolderList.return_value = []
        pool = mock.Mock()
        pool.GetRootFolder.return_value = root
        project = mock.Mock()
        project.GetMediaPool.return_value = pool
        resolve = mock.Mock()
        resolve.GetProjectManager.return_value.GetCurrentProject.return_value = project
        return resolve, clips

    def test_writes_to_matching_clip_with_script_defaults(self):
        resolve, clips = self.make_resolve(['/Volumes/Drive/shot.MP4'])
        r = {'meta': {}, 'display': {}}
        with mock.patch('slogmetaraw.resolve_io.apply_to_clip',
                        return_value={'written': ['A', 'B'], 'failed': [], 'color_space': None}) as apply:
            report = connect.apply_path(resolve, '/Volumes/Drive/shot.MP4', r)
        self.assertEqual(report, {'written': 2, 'failed': 0, 'clips': 1, 'data_level': {}})
        apply.assert_called_once_with(clips[0], r, set_color_space=False, overwrite=True, add_tags=False,
                                     set_data_level=True)

    def test_matches_real_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            real = os.path.join(directory, 'clip.MP4')
            with open(real, 'w') as fh:
                fh.write('x')
            link = os.path.join(directory, 'alias.MP4')
            os.symlink(real, link)
            resolve, _ = self.make_resolve([link])
            r = {'meta': {}, 'display': {}}
            with mock.patch('slogmetaraw.resolve_io.apply_to_clip',
                            return_value={'written': ['A'], 'failed': [], 'color_space': None}) as apply:
                report = connect.apply_path(resolve, real, r)
        self.assertEqual(report['clips'], 1)
        apply.assert_called_once()

    def test_clip_not_in_pool_raises(self):
        resolve, _ = self.make_resolve(['/other/clip.MP4'])
        with self.assertRaisesRegex(RuntimeError, 'Media Pool'):
            connect.apply_path(resolve, '/wanted/clip.MP4', {'meta': {}, 'display': {}})

    def test_no_project_raises(self):
        resolve = mock.Mock()
        resolve.GetProjectManager.return_value.GetCurrentProject.return_value = None
        with self.assertRaisesRegex(RuntimeError, 'progetto'):
            connect.apply_path(resolve, '/x.MP4', {'meta': {}, 'display': {}})


if __name__ == '__main__':
    unittest.main()
