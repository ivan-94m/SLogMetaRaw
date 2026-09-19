# SPDX-License-Identifier: GPL-3.0-or-later
"""CLI: python3 -m slogmetaraw [--json] [--interval S] PATH [PATH...]  (files or folders)."""
import argparse
import json
import os
import sys
import time

from .extract import read_clip, DatalessError

EXTS = ('.mp4', '.mxf')


def iter_clips(paths):
    for p in paths:
        if os.path.isdir(p):
            for root, _dirs, files in os.walk(p):
                for n in sorted(files):
                    if n.lower().endswith(EXTS) and not n.startswith('._'):
                        yield os.path.join(root, n)
        else:
            yield p


def _jsonable(o):
    if isinstance(o, bytes):
        return '<%d bytes>' % len(o)
    if isinstance(o, tuple):
        return list(o)
    return str(o)


def main(argv=None):
    ap = argparse.ArgumentParser(prog='slogmetaraw')
    ap.add_argument('paths', nargs='+')
    ap.add_argument('--json', action='store_true', help='print full JSON')
    ap.add_argument('--interval', type=float, default=1.0, help='seconds between sampled frames')
    ap.add_argument('--cache', action='store_true',
                    help='write the SLogMetaRaw plugin records and print their paths')
    a = ap.parse_args(argv)
    if a.cache:
        from .plugin_cache import write_cache
        status = 0
        for path in iter_clips(a.paths):
            try:
                print(write_cache(read_clip(path, interval=a.interval)))
            except Exception as exc:  # report and continue with the next clip
                print('ERROR %s: %s' % (path, exc), file=sys.stderr)
                status = 1
        return status
    results = []
    for path in iter_clips(a.paths):
        t0 = time.time()
        try:
            r = read_clip(path, interval=a.interval)
        except DatalessError as e:
            print('SKIP', e, file=sys.stderr)
            continue
        r['elapsed_s'] = round(time.time() - t0, 3)
        r.pop('embedded_lut', None)
        results.append(r)
        if not a.json:
            print('=' * 78)
            print('%s   [%s, letti %.1f KB di %.1f MB in %.2fs]' % (
                path, r['container'], r['bytes_read'] / 1024, r['file_size'] / 1e6, r['elapsed_s']))
            for title, rows in r['sections']:
                if not rows:
                    continue
                print('  --- %s' % title)
                for label, val in rows:
                    print('    %-40s %s' % (label, val))
            for w in r['warnings']:
                print('  ! ' + w)
    if a.json:
        json.dump(results, sys.stdout, indent=1, default=_jsonable, ensure_ascii=False)


if __name__ == '__main__':
    sys.exit(main())
