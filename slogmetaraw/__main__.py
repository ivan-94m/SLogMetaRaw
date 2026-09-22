# SPDX-License-Identifier: GPL-3.0-or-later
"""CLI: python3 -m slogmetaraw [--json] [--interval S] PATH [PATH...]  (files or folders).

Internal modes: --helper (streaming reader for the script window) and --to-resolve
(one clip: read + write into Resolve, used by the OpenFX plugin button)."""
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


def _helper(interval):
    """Streaming mode used by the script window (ui.py): one clip path per line on
    stdin, one JSON result per line on stdout. A clip that hangs can be killed from
    outside (the window enforces a per-clip timeout), so the scan always finishes."""
    for line in sys.stdin:
        path = line.strip()
        if not path:
            continue
        try:
            r = read_clip(path, interval=interval)
            r.pop('embedded_lut', None)
            print(json.dumps({'path': path, 'ok': True, 'result': r},
                             default=_jsonable, ensure_ascii=False), flush=True)
        except DatalessError as exc:
            print(json.dumps({'path': path, 'ok': False, 'kind': 'dataless', 'error': str(exc)},
                             ensure_ascii=False), flush=True)
        except Exception as exc:
            print(json.dumps({'path': path, 'ok': False, 'kind': 'error', 'error': str(exc)},
                             ensure_ascii=False), flush=True)
    return 0


def to_resolve(paths):
    """One clip for the plugin's "Rileggi metadata" button.

    Reads the metadata from the file, refreshes the plugin cache record, then
    writes the metadata into the matching Media Pool clip in Resolve. Prints one
    flat JSON line on stdout: the plugin parses it and shows the outcome in its
    status field. Exit code 1 only when the metadata could not be read at all."""
    if not paths:
        print(json.dumps({'ok': 0, 'error': 'manca il percorso della clip'}, ensure_ascii=False), flush=True)
        return 1
    path = paths[0]
    try:
        r = read_clip(path)
    except Exception as exc:
        print(json.dumps({'ok': 0, 'error': 'lettura metadata: %s' % exc}, ensure_ascii=False), flush=True)
        return 1
    from .plugin_cache import write_cache
    cache_error = ''
    try:
        write_cache(r)
    except OSError as exc:
        cache_error = str(exc)
    try:
        if os.environ.get('SLOGMETARAW_TEST_NO_RESOLVE'):
            raise RuntimeError('scrittura in Resolve disabilitata (ambiente di test)')
        from .connect import apply_path, connect
        report = apply_path(connect(), path, r)
        level = report.get('data_level') or {}
        print(json.dumps({'ok': 1, 'written': report['written'], 'failed': report['failed'],
                          'clips': report['clips'], 'cache': cache_error,
                          'data_level': r['meta'].get('data_level') or '',
                          'level_host': level.get('host') or ''}, ensure_ascii=False), flush=True)
        return 0
    except Exception as exc:
        print(json.dumps({'ok': 0, 'error': str(exc), 'cache': cache_error}, ensure_ascii=False), flush=True)
        return 1


def main(argv=None):
    ap = argparse.ArgumentParser(prog='slogmetaraw')
    ap.add_argument('paths', nargs='*')
    ap.add_argument('--json', action='store_true', help='print full JSON')
    ap.add_argument('--interval', type=float, default=1.0, help='seconds between sampled frames')
    ap.add_argument('--cache', action='store_true',
                    help='write the SLogMetaRaw plugin records and print their paths')
    ap.add_argument('--helper', action='store_true', help=argparse.SUPPRESS)
    ap.add_argument('--to-resolve', action='store_true',
                    help='legge i metadata di una clip e li scrive nel Media Pool di Resolve')
    a = ap.parse_args(argv)
    if a.helper:
        return _helper(a.interval)
    if a.to_resolve:
        return to_resolve(a.paths)
    if not a.paths:
        ap.error('servono uno o più percorsi (file o cartelle)')
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
    status = 0
    for path in iter_clips(a.paths):
        t0 = time.time()
        try:
            r = read_clip(path, interval=a.interval)
        except DatalessError as e:
            print('SKIP', e, file=sys.stderr)
            continue
        except Exception as exc:  # a malformed clip must not stop the others
            print('ERROR %s: %s' % (path, exc), file=sys.stderr)
            status = 1
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
    return status


if __name__ == '__main__':
    sys.exit(main())
