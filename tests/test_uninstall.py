# SPDX-License-Identifier: GPL-3.0-or-later
"""The uninstaller and the installer's preinstall, on a fake Mac (a temporary root and home).

They run with /bin/bash, the 3.2 macOS uses for .command files and package scripts.
"""
import os
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNINSTALL = os.path.join(ROOT, 'packaging', 'Disinstalla S-Log MetaRaw.command')
PREINSTALL = os.path.join(ROOT, 'packaging', 'scripts', 'preinstall')
UTIL = 'Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility'
OFX_CACHE = 'Library/Application Support/Blackmagic Design/DaVinci Resolve/OFXPluginCacheV2.xml'

# every place any version ever wrote to: 2.x, 1.x, the old SonyMeta name, developer installs, the test probe
SYSTEM = ['Library/OFX/Plugins/SLogMetaRaw.ofx.bundle/Contents/MacOS/SLogMetaRaw.ofx',
          'Library/OFX/Plugins/SLogMetaRawProbe.ofx.bundle/Contents/Info.plist',
          'Library/OFX/Plugins/SonyMetaRAW.ofx.bundle/Contents/Info.plist',
          'Library/Application Support/SLogMetaRaw/lib/slogmetaraw/__init__.py',
          'Library/Application Support/SonyMeta/lib/sonymeta.py',
          UTIL + '/S-Log MetaRaw.py', UTIL + '/SLogMetaRaw.py', UTIL + '/SonyMeta.py']
USER = [UTIL + '/S-Log MetaRaw.py', UTIL + '/SLogMetaRaw.py', UTIL + '/SonyMeta.py',
        'Library/Application Support/SLogMetaRaw/cache/0123456789abcdef.json',
        'Library/Application Support/SLogMetaRaw/update.json',
        'Library/Application Support/SLogMetaRaw/no_update_check',
        'Library/Application Support/SLogMetaRaw/lib_path',
        'Library/Application Support/SLogMetaRaw/lib/slogmetaraw/__init__.py',
        'Library/Application Support/SLogMetaRaw/pycache/x.pyc',
        'Library/Application Support/SonyMeta/cache.json',
        'Library/Logs/SLogMetaRaw/plugin-child.log', 'Library/Logs/SonyMeta/x.log', OFX_CACHE]
# what must survive: somebody else's plugin and scripts, Resolve's own data, the user's clips
UNRELATED = ['Library/OFX/Plugins/Other.ofx.bundle/Contents/Info.plist', UTIL + '/Other.py',
             'Library/Application Support/Blackmagic Design/DaVinci Resolve/Preferences/config.dat']
CSV = 'Documents/SLogMetaRaw/export.csv'


def touch(base, rel):
    path = os.path.join(base, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as fh:
        fh.write('x')
    return path


class FakeMac:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, 'root')
        self.home = os.path.join(self.tmp.name, 'home')
        for rel in SYSTEM + UNRELATED:
            touch(self.root, rel)
        for rel in USER + UNRELATED + [CSV, 'Movies/clip.MP4']:
            touch(self.home, rel)

    def env(self, **extra):
        env = dict(os.environ, HOME=self.home, SLOGMETARAW_ROOT=self.root, SLOGMETARAW_NO_SUDO='1',
                   SLOGMETARAW_IGNORE_RESOLVE='1')
        env.update(extra)
        return env

    def run(self, script, *args, stdin='', **env):
        return subprocess.run(['/bin/bash', script, *args], input=stdin, env=self.env(**env),
                              capture_output=True, text=True, timeout=60)

    def left(self):
        return [r for r in SYSTEM if os.path.lexists(os.path.join(self.root, r))] + \
               [r for r in USER if os.path.lexists(os.path.join(self.home, r))]


class Uninstaller(unittest.TestCase):
    def setUp(self):
        self.mac = FakeMac()
        self.addCleanup(self.mac.tmp.cleanup)

    def test_it_removes_every_version_and_nothing_else(self):
        run = self.mac.run(UNINSTALL, SLOGMETARAW_YES='1')
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual(self.mac.left(), [])
        for rel in UNRELATED:
            self.assertTrue(os.path.exists(os.path.join(self.mac.root, rel)), rel)
            self.assertTrue(os.path.exists(os.path.join(self.mac.home, rel)), rel)
        self.assertTrue(os.path.exists(os.path.join(self.mac.home, 'Movies/clip.MP4')))
        self.assertIn('rimosso del tutto', run.stdout)

    def test_csv_exports_stay_unless_asked(self):
        self.mac.run(UNINSTALL, SLOGMETARAW_YES='1')
        self.assertTrue(os.path.exists(os.path.join(self.mac.home, CSV)))
        mac = FakeMac()
        self.addCleanup(mac.tmp.cleanup)
        mac.run(UNINSTALL, SLOGMETARAW_YES='1', SLOGMETARAW_DELETE_CSV='1')
        self.assertFalse(os.path.exists(os.path.join(mac.home, 'Documents/SLogMetaRaw')))

    def test_answering_no_removes_nothing(self):
        run = self.mac.run(UNINSTALL, stdin='n\n')
        self.assertIn('Annullato', run.stdout)
        self.assertEqual(len(self.mac.left()), len(SYSTEM) + len(USER))

    def test_the_interactive_path_asks_about_the_csv(self):
        run = self.mac.run(UNINSTALL, stdin='s\nn\n')
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual(self.mac.left(), [])
        self.assertTrue(os.path.exists(os.path.join(self.mac.home, CSV)))

    def test_dry_run_lists_and_removes_nothing(self):
        run = self.mac.run(UNINSTALL, '--dry-run')
        self.assertEqual(len(self.mac.left()), len(SYSTEM) + len(USER))
        self.assertIn('SLogMetaRaw.ofx.bundle', run.stdout)
        self.assertIn('non è stato rimosso niente', run.stdout)

    def test_a_developer_install_loses_its_link_not_the_working_copy(self):
        plugin = os.path.join(self.mac.root, 'Library/OFX/Plugins/SLogMetaRaw.ofx.bundle')
        subprocess.run(['rm', '-rf', plugin], check=True)
        work = os.path.join(self.mac.tmp.name, 'work', 'SLogMetaRaw.ofx.bundle')
        touch(work, 'Contents/MacOS/SLogMetaRaw.ofx')
        os.symlink(work, plugin)
        self.mac.run(UNINSTALL, SLOGMETARAW_YES='1')
        self.assertFalse(os.path.lexists(plugin))
        self.assertTrue(os.path.exists(os.path.join(work, 'Contents/MacOS/SLogMetaRaw.ofx')))

    def test_nothing_installed_says_so(self):
        self.mac.run(UNINSTALL, SLOGMETARAW_YES='1')
        run = self.mac.run(UNINSTALL, SLOGMETARAW_YES='1')
        self.assertEqual(run.returncode, 0)
        self.assertIn('niente da rimuovere', run.stdout)


class Preinstall(unittest.TestCase):
    def setUp(self):
        self.mac = FakeMac()
        self.addCleanup(self.mac.tmp.cleanup)

    def test_every_install_starts_clean(self):
        stale = touch(self.mac.root, 'Library/OFX/Plugins/SLogMetaRaw.ofx.bundle/Contents/Resources/old_icon.png')
        run = self.mac.run(PREINSTALL, SLOGMETARAW_HOME=self.mac.home)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertFalse(os.path.exists(stale))
        gone = ['Library/OFX/Plugins/SLogMetaRaw.ofx.bundle', 'Library/OFX/Plugins/SLogMetaRawProbe.ofx.bundle',
                'Library/OFX/Plugins/SonyMetaRAW.ofx.bundle', 'Library/Application Support/SLogMetaRaw/lib',
                UTIL + '/SLogMetaRaw.py', UTIL + '/SonyMeta.py', UTIL + '/S-Log MetaRaw.py']
        for rel in gone:
            self.assertFalse(os.path.lexists(os.path.join(self.mac.root, rel)), rel)
        for rel in ('Library/Application Support/SLogMetaRaw/lib_path', 'Library/Application Support/SLogMetaRaw/lib',
                    'Library/Application Support/SLogMetaRaw/pycache', UTIL + '/S-Log MetaRaw.py', OFX_CACHE):
            self.assertFalse(os.path.lexists(os.path.join(self.mac.home, rel)), rel)
        # what is worth keeping across an update: the metadata records and the update settings
        for rel in ('Library/Application Support/SLogMetaRaw/cache/0123456789abcdef.json',
                    'Library/Application Support/SLogMetaRaw/no_update_check', CSV):
            self.assertTrue(os.path.exists(os.path.join(self.mac.home, rel)), rel)
        for rel in UNRELATED:
            self.assertTrue(os.path.exists(os.path.join(self.mac.root, rel)), rel)


if __name__ == '__main__':
    unittest.main()
