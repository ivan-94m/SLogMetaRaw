# SPDX-License-Identifier: GPL-3.0-or-later
"""Damaged and truncated clips: the reader returns what it can, never hangs or raises."""
import os
import random
import shutil
import signal
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tests'))

from slogmetaraw import read_clip, extract, mp4, mxf  # noqa: E402
import clip_fixtures as fx  # noqa: E402


class _Timeout(Exception):
    pass


def _alarm(*_):
    raise _Timeout()


class Damaged(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp()
        cls.mp4 = os.path.join(cls.dir, 'C0001.MP4')
        cls.mxf = os.path.join(cls.dir, 'C0002.MXF')
        fx.build_mp4(cls.mp4, frames=50)
        fx.build_mxf(cls.mxf, frames=10, header_fill=64 * 1024)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def setUp(self):
        if not hasattr(signal, 'SIGALRM'):
            self.skipTest('SIGALRM non disponibile')
        self._old = signal.signal(signal.SIGALRM, _alarm)

    def tearDown(self):
        signal.alarm(0)
        signal.signal(signal.SIGALRM, self._old)

    def _read(self, data, name):
        path = os.path.join(self.dir, 'bad_' + name)
        with open(path, 'wb') as fh:
            fh.write(data)
        signal.alarm(5)
        try:
            read_clip(path)
        except _Timeout:
            self.fail('lettura bloccata: %s' % name)
        except (ValueError, OSError):
            pass   # a clean refusal is fine; a hang or a stray struct/Index/KeyError is not
        finally:
            signal.alarm(0)

    def test_truncated_and_corrupted_clips(self):
        rnd = random.Random(7)
        for src in (self.mp4, self.mxf):
            with open(src, 'rb') as fh:
                data = fh.read()
            name = os.path.basename(src)
            for cut in (len(data) // 7, len(data) // 3, len(data) // 2, len(data) - 9):
                self._read(data[:cut], name)
            for _ in range(60):
                b = bytearray(data)
                for _ in range(8):
                    b[rnd.randrange(len(b))] = rnd.randrange(256)
                self._read(bytes(b), name)

    def test_zero_samples_per_chunk_does_not_walk_billions_of_chunks(self):
        t = mp4.Track()
        t.tables[b'stsz'] = bytes(4) + (100).to_bytes(4, 'big') + (10).to_bytes(4, 'big')
        t.tables[b'stco'] = bytes(4) + (1).to_bytes(4, 'big') + (0).to_bytes(4, 'big')
        runs = [(1, 0, 1), (0xFFFFFFF0, 1, 1)]
        t.tables[b'stsc'] = bytes(4) + len(runs).to_bytes(4, 'big') + b''.join(
            a.to_bytes(4, 'big') + b.to_bytes(4, 'big') + c.to_bytes(4, 'big') for a, b, c in runs)
        signal.alarm(5)
        self.assertEqual(t.sample_offsets([0, 5]), {})

    def test_a_file_that_shrinks_ends_the_byte_scan(self):
        class Short:
            size = 64 * 1024 * 1024

            def read_at(self, pos, n):
                return b''
        signal.alarm(5)
        self.assertIsNone(mxf.find_rtmd(Short(), 0))
        self.assertEqual(mxf.find_sps(Short()), (None, None))

    def test_a_damaged_nrt_keeps_the_rest_of_the_record(self):
        out = {'meta': {}, 'warnings': []}
        extract._merge_nrt(out, b'<NonRealTimeMeta><Duration value="x"')
        self.assertEqual(out['meta'], {})
        self.assertTrue(out['warnings'])


if __name__ == '__main__':
    unittest.main()
