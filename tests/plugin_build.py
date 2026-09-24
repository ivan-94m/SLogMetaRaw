# SPDX-License-Identifier: GPL-3.0-or-later
"""Paths of the built plugin and its test binaries; `make test-bins` compiles them with the shipped flags."""
import glob
import os
import shutil
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OFX = os.path.join(ROOT, 'ofx', 'SLogMetaRaw')
BUNDLE_BINARY = os.path.join(OFX, 'SLogMetaRaw.ofx.bundle', 'Contents', 'MacOS', 'SLogMetaRaw.ofx')
_built = None


def test_bin(name):
    """Path of build/tests/<name>, after one `make test-bins` per test run; None when it cannot be built."""
    global _built
    if _built is None:
        _built = bool(shutil.which('make') and shutil.which('clang++')) and subprocess.run(
            ['make', '-s', '-C', OFX, 'all', 'test-bins'], capture_output=True).returncode == 0
    path = os.path.join(OFX, 'build', 'tests', name)
    return path if _built and os.path.exists(path) else None


def rosetta():
    """True when the x86_64 slice of a universal binary can run here."""
    return subprocess.run(['arch', '-x86_64', '/usr/bin/true'], capture_output=True).returncode == 0


def source():
    """All plugin sources (src/**/*.h, *.cpp) concatenated, for the checks that read the code."""
    parts = []
    for path in sorted(glob.glob(os.path.join(OFX, 'src', '**', '*.*'), recursive=True)):
        if path.endswith(('.h', '.cpp')):
            with open(path, encoding='utf-8') as fh:
                parts.append(fh.read())
    return '\n'.join(parts)


def body(src, signature):
    """Text of the function whose definition starts with `signature`, up to its closing brace."""
    start = src.index(signature)
    return src[start:src.index('\n}\n', start) + 2]
