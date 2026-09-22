# SPDX-License-Identifier: GPL-3.0-or-later
"""Exercise launcher generation and isolated installs, without system writes."""
import ast
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_FOLDER = Path('Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility')
SUPPORT_FOLDER = Path('Library/Application Support/SLogMetaRaw')


def library_in_launcher(path):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == 'LIB_DIR' for target in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError('No LIB_DIR assignment in launcher')


class LauncherRendering(unittest.TestCase):
    def test_special_characters_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'S-Log MetaRaw.py'
            library = str(Path(directory) / 'libreria d\'Ivan & altri | "è" \\ cartella\nnuova')
            result = subprocess.run([sys.executable, str(ROOT / 'tools/render_launcher.py'),
                                     str(ROOT / 'resolve_script/SLogMetaRaw.py'), library, str(output)],
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(library_in_launcher(output), library)
            compile(output.read_text(encoding='utf-8'), str(output), 'exec')

    def test_invalid_template_preserves_installed_launcher(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'template.py'
            source.write_text("LIB_DIR = '__LIB_DIR__'\nthis is broken Python\n", encoding='utf-8')
            output = Path(directory) / 'installed.py'
            output.write_text('previous launcher', encoding='utf-8')
            result = subprocess.run([sys.executable, str(ROOT / 'tools/render_launcher.py'),
                                     str(source), directory, str(output)],
                                    capture_output=True, text=True, timeout=15)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(output.read_text(encoding='utf-8'), 'previous launcher')
            self.assertEqual(list(Path(directory).glob('.slogmetaraw-*')), [])


class ScriptOnlyInstall(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.checkout = self.directory / "checkout d'Ivan & | è"
        self.user_directory = self.directory / "user d'Ivan & | è"
        self.checkout.mkdir()
        self.user_directory.mkdir()
        shutil.copy2(ROOT / 'install.sh', self.checkout / 'install.sh')
        for subdirectory in ('resolve_script', 'tools', 'slogmetaraw'):
            (self.checkout / subdirectory).mkdir()
        shutil.copy2(ROOT / 'resolve_script/SLogMetaRaw.py', self.checkout / 'resolve_script/SLogMetaRaw.py')
        shutil.copy2(ROOT / 'tools/render_launcher.py', self.checkout / 'tools/render_launcher.py')
        (self.checkout / 'slogmetaraw/__init__.py').write_text("VERSION = 'test'\n", encoding='utf-8')
        (self.checkout / 'ofx/SLogMetaRaw/SLogMetaRaw.ofx.bundle').mkdir(parents=True)
        # Even with a built plugin present, --script-only must never invoke sudo.
        fake_bin = self.directory / 'bin'
        fake_bin.mkdir()
        fake_sudo = fake_bin / 'sudo'
        fake_sudo.write_text('#!/bin/sh\nprintf invoked > "$SLOGMETARAW_TEST_SUDO_LOG"\nexit 99\n', encoding='utf-8')
        fake_sudo.chmod(0o755)
        self.sudo_log = self.directory / 'sudo.log'
        self.environment = dict(os.environ, HOME=str(self.user_directory),
                                PATH=str(fake_bin) + os.pathsep + os.environ['PATH'],
                                SLOGMETARAW_TEST_SUDO_LOG=str(self.sudo_log))

    def install(self, *arguments):
        return subprocess.run(['/bin/bash', str(self.checkout / 'install.sh'), *arguments],
                              env=self.environment, capture_output=True, text=True, timeout=30)

    def test_dev_script_only_is_independent_of_argument_order(self):
        for arguments in (('--dev', '--script-only'), ('--script-only', '--dev')):
            with self.subTest(arguments=arguments):
                result = self.install(*arguments)
                self.assertEqual(result.returncode, 0, result.stderr)
                launcher = self.user_directory / SCRIPT_FOLDER / 'S-Log MetaRaw.py'
                self.assertEqual(library_in_launcher(launcher), str(self.checkout))
                pointer = self.user_directory / SUPPORT_FOLDER / 'lib_path'
                self.assertEqual(pointer.read_text(encoding='utf-8').strip(), str(self.checkout))
                self.assertFalse(self.sudo_log.exists())

    def test_copy_script_only_updates_library_and_removes_old_menu_aliases(self):
        scripts = self.user_directory / SCRIPT_FOLDER
        scripts.mkdir(parents=True)
        for alias in ('SonyMeta.py', 'SLogMetaRaw.py'):
            (scripts / alias).write_text('old launcher', encoding='utf-8')
        result = self.install('--script-only')
        self.assertEqual(result.returncode, 0, result.stderr)
        installed_library = self.user_directory / SUPPORT_FOLDER / 'lib'
        self.assertEqual(library_in_launcher(scripts / 'S-Log MetaRaw.py'), str(installed_library))
        self.assertEqual((installed_library / 'slogmetaraw/__init__.py').read_text(encoding='utf-8'),
                         "VERSION = 'test'\n")
        self.assertFalse((scripts / 'SonyMeta.py').exists())
        self.assertFalse((scripts / 'SLogMetaRaw.py').exists())
        self.assertFalse(self.sudo_log.exists())

    def test_unknown_option_does_not_install(self):
        result = self.install('--invalid')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(list(self.user_directory.iterdir()), [])
        self.assertFalse(self.sudo_log.exists())


class Versioning(unittest.TestCase):
    """The version must live in one place. It used to be written by hand in
    distribution.xml as well, so the disk image could say 1.1.0 while the installer
    window still said 1.0.1."""

    def test_the_package_scripts_are_executable(self):
        """macOS runs preinstall and postinstall with execve. Without the mode bit it
        fails and PackageKit reports "the file does not exist", which stops the whole
        installation with a useless message. The bit has to survive a fresh clone, so
        it is checked on disk, in the git index, and forced again at build time."""
        import stat as statmod
        import subprocess
        scripts = os.path.join(ROOT, 'packaging', 'scripts')
        names = sorted(os.listdir(scripts))
        self.assertTrue(names, 'nessuno script di pacchetto')
        for name in names:
            mode = os.stat(os.path.join(scripts, name)).st_mode
            self.assertTrue(mode & statmod.S_IXUSR, '%s non e eseguibile' % name)
        listing = subprocess.run(['git', 'ls-files', '-s', 'packaging/scripts'],
                                 cwd=ROOT, capture_output=True, text=True)
        if listing.returncode == 0 and listing.stdout.strip():
            for line in listing.stdout.strip().splitlines():
                self.assertTrue(line.startswith('100755'),
                                'git non registra il bit di esecuzione: %s' % line)
        with open(os.path.join(ROOT, 'packaging', 'build_installer.sh'), encoding='utf-8') as fh:
            self.assertIn('chmod +x "$PKG_DIR/scripts/preinstall"', fh.read(),
                          'il build non forza il bit di esecuzione')

    def test_the_package_scripts_always_succeed(self):
        """They only clean up leftovers. If one returned non-zero the installer would
        abort even though nothing was wrong."""
        scripts = os.path.join(ROOT, 'packaging', 'scripts')
        for name in sorted(os.listdir(scripts)):
            with open(os.path.join(scripts, name), encoding='utf-8') as fh:
                body = fh.read()
            self.assertTrue(body.startswith('#!/bin/bash'), '%s: shebang mancante' % name)
            self.assertIn('exit 0', body, '%s non termina con exit 0' % name)

    def test_nothing_under_packaging_hardcodes_a_version(self):
        """Every file the installer shows the user. Checking only distribution.xml
        was not enough: welcome.html carried its own copy and went on announcing the
        previous version on a disk built from the new one."""
        import re
        pkg = os.path.join(ROOT, 'packaging')
        for folder, _dirs, files in os.walk(pkg):
            for name in files:
                if not name.endswith(('.html', '.xml')):
                    continue
                path = os.path.join(folder, name)
                with open(path, encoding='utf-8') as fh:
                    text = fh.read()
                found = re.findall(r'\b\d+\.\d+\.\d+\b', text)
                self.assertEqual(found, [], '%s ha una versione fissa: %s'
                                 % (os.path.relpath(path, ROOT), found))

    def test_the_installer_takes_the_version_from_the_package(self):
        with open(os.path.join(ROOT, 'packaging', 'distribution.xml'), encoding='utf-8') as fh:
            self.assertEqual(fh.read().count('@VERSION@'), 2, 'la versione e di nuovo scritta a mano')
        with open(os.path.join(ROOT, 'packaging', 'resources', 'welcome.html'), encoding='utf-8') as fh:
            self.assertIn('@VERSION@', fh.read(), 'la pagina di benvenuto non dichiara la versione')
        with open(os.path.join(ROOT, 'packaging', 'build_installer.sh'), encoding='utf-8') as fh:
            script = fh.read()
        self.assertIn('slogmetaraw.__version__', script)
        self.assertIn('"$BUILD/distribution.xml"', script, 'distribution.xml non viene sostituito')
        self.assertIn('"$BUILD/resources/"*.html', script, 'le pagine html non vengono sostituite')


if __name__ == '__main__':
    unittest.main()
