# SPDX-License-Identifier: GPL-3.0-or-later
"""CLI: python3 -m slogmetaraw [--json] [--interval S] [--max-samples N] PATH [PATH...]
(files or folders).

Modes used by the OpenFX plugin (argument order and flat JSON output are its contract):
  --cache PATH [PATH...] [--max-samples N] [--deadline S]
  --to-resolve PATH
  --update-check [--current X] [--force]
and --helper, the streaming reader of the script window."""
import json
import math
import os
import signal
import stat
import sys
import time

from .extract import read_clip, DatalessError, FULL_SAMPLES

EXTS = ('.mp4', '.mxf')
CACHE_SAMPLES = 8
CACHE_DEADLINE = 15.0
CLIP_BUDGET = 1.0         # seconds of sampling per clip for the script and --to-resolve
RESOLVE_CONNECT = 3.0
RESOLVE_WRITE = 15.0
RESOLVE_ALARM = 20        # hard limit of the detached writer, above connect + write
UPDATE_TTL = 24 * 3600


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


def _emit(obj):
    print(json.dumps(obj, ensure_ascii=False), flush=True)


def _helper(interval, max_samples=FULL_SAMPLES, budget=CLIP_BUDGET):
    """Streaming mode used by the script window (ui.py): one clip path per line on
    stdin, one JSON result per line on stdout. A clip that hangs can be killed from
    outside (the window enforces a per-clip timeout), so the scan always finishes."""
    for line in sys.stdin:
        path = line.strip()
        if not path:
            continue
        try:
            r = read_clip(path, interval=interval, max_samples=max_samples,
                          deadline=time.monotonic() + budget)
            print(json.dumps({'path': path, 'ok': True, 'result': r},
                             default=_jsonable, ensure_ascii=False), flush=True)
        except DatalessError as exc:
            _emit({'path': path, 'ok': False, 'kind': 'dataless', 'error': str(exc)})
        except Exception as exc:
            _emit({'path': path, 'ok': False, 'kind': 'error', 'error': str(exc)})
    return 0


def cache_clips(paths, interval=1.0, max_samples=CACHE_SAMPLES, deadline_s=CACHE_DEADLINE):
    """Write the plugin records; prints each record path, errors on stderr. 0 if all were written."""
    from .plugin_cache import write_cache
    deadline = time.monotonic() + deadline_s
    status = 0
    for path in iter_clips(paths):
        try:
            if time.monotonic() >= deadline:
                raise TimeoutError('tempo scaduto (%g s)' % deadline_s)
            r = read_clip(path, interval=interval, max_samples=max_samples, deadline=deadline)
            print(write_cache(r, keep_complete=True), flush=True)
        except Exception as exc:  # report and continue with the next clip
            print('ERROR %s: %s' % (path, exc), file=sys.stderr)
            status = 1
    return status


def _cache_cli(args, hard_limit):
    """--cache without argparse: the plugin starts one of these per clip it cannot find."""
    paths, opts = [], {'--max-samples': CACHE_SAMPLES, '--deadline': CACHE_DEADLINE, '--interval': 1.0}
    it = iter(args)
    for arg in it:
        if arg in opts:
            try:
                opts[arg] = type(opts[arg])(next(it))
            except (StopIteration, ValueError):
                print('ERROR valore mancante o non valido per %s' % arg, file=sys.stderr)
                return 2
        else:
            paths.append(arg)
    if not paths:
        print('ERROR servono uno o più percorsi', file=sys.stderr)
        return 2
    if hard_limit:
        # a pread blocked on a dead volume never reaches the soft deadline checks
        signal.alarm(int(math.ceil(opts['--deadline'])) + 1)
    return cache_clips(paths, opts['--interval'], opts['--max-samples'], opts['--deadline'])


# --- "Rileggi metadata" ------------------------------------------------------

def _status(**values):
    return dict({'ok': 0, 'written': 0, 'failed': 0, 'clips': 0, 'level_host': '', 'error': ''}, **values)


def write_to_resolve(path, r, on_connected=None):
    """Write one clip into the Media Pool; returns the flat status the plugin reads back."""
    status = _status()
    try:
        if os.environ.get('SLOGMETARAW_TEST_NO_RESOLVE'):
            raise RuntimeError('scrittura in Resolve disabilitata (ambiente di test)')
        from . import connect
        resolve = connect.connect()
        if on_connected:
            on_connected()
        report = connect.apply_path(resolve, path, r)
    except Exception as exc:
        status['error'] = str(exc)
        return status
    status.update(ok=1, written=report['written'], failed=report['failed'], clips=report['clips'],
                  level_host=(report.get('data_level') or {}).get('host') or '')
    return status


def _save_status(path, status):
    tmp = '%s.%d.tmp' % (path, os.getpid())
    try:
        with open(tmp, 'w', encoding='utf-8') as fh:
            json.dump(status, fh, ensure_ascii=False)
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _resolve_writer(path, r, status_path):
    """Body of the detached grandchild: bounded connection and write, then the status file.

    The Resolve calls stay on the main thread; a watchdog thread writes the timeout
    status and ends the process, since a call blocked inside fusionscript never returns.
    """
    import threading
    lock = threading.Lock()
    finished = []
    connected, done = threading.Event(), threading.Event()

    def finish(status):
        with lock:
            if not finished:
                finished.append(True)
                _save_status(status_path, status)

    def watchdog():
        if not connected.wait(RESOLVE_CONNECT):
            error = 'DaVinci Resolve non risponde (connessione oltre %d s)' % RESOLVE_CONNECT
        elif not done.wait(RESOLVE_WRITE):
            error = 'scrittura in Resolve oltre %d s' % RESOLVE_WRITE
        else:
            return
        finish(_status(error=error))
        os._exit(0)

    threading.Thread(target=watchdog, daemon=True).start()
    status = write_to_resolve(path, r, on_connected=connected.set)
    finish(status)
    connected.set()
    done.set()


def _detach(job):
    """Run job in a grandchild with its own session; the caller returns at once."""
    sys.stdout.flush()
    sys.stderr.flush()
    pid = os.fork()
    if pid:
        os.waitpid(pid, 0)   # the intermediate child exits right away
        return
    try:
        os.setsid()
        if os.fork():
            os._exit(0)
        # the plugin waits for EOF on stdout: the grandchild must not hold the pipe
        null = os.open(os.devnull, os.O_RDWR)
        os.dup2(null, 0)
        os.dup2(null, 1)
        try:
            keep_stderr = stat.S_ISREG(os.fstat(2).st_mode)   # the plugin's log file
        except OSError:
            keep_stderr = False
        if not keep_stderr:
            os.dup2(null, 2)
        signal.alarm(RESOLVE_ALARM)
        job()
    finally:
        os._exit(0)


def to_resolve(paths, detach=True):
    """One clip for the plugin's "Rileggi metadata" button.

    Reads the clip (budget CLIP_BUDGET), refreshes the plugin record and prints one
    flat JSON line at once: {"cache": 1} or {"cache": 0, "error": ...}. The write
    into Resolve then runs detached; its outcome lands in <fnv>.resolve.json next to
    the record. Exit code 1 only when the clip could not be read."""
    if not paths:
        _emit({'cache': 0, 'error': 'manca il percorso della clip'})
        return 1
    path = paths[0]
    from . import plugin_cache
    status_path = plugin_cache.resolve_status_path(path)
    try:
        os.unlink(status_path)   # never show the outcome of an earlier press
    except OSError:
        pass
    try:
        r = read_clip(path, max_samples=FULL_SAMPLES, deadline=time.monotonic() + CLIP_BUDGET)
    except Exception as exc:
        _emit({'cache': 0, 'error': 'lettura metadata: %s' % exc})
        return 1
    try:
        plugin_cache.write_cache(r)
        _emit({'cache': 1})
    except OSError as exc:
        _emit({'cache': 0, 'error': 'scheda per il plugin non salvata: %s' % exc})
    if detach:
        _detach(lambda: _resolve_writer(path, r, status_path))
    else:
        _save_status(status_path, write_to_resolve(path, r))
    return 0


# --- update check for the plugin's version button ----------------------------

def update_check(current='', force=False):
    """One flat JSON line (strings and 0/1 integers) about the newest release; exit 0 even offline.

    A result younger than UPDATE_TTL is reused, so the automatic check of the
    plugin reaches GitHub at most once a day; force (a click) asks again.
    """
    from . import update, __version__
    cur = current or __version__
    try:
        st = update.read_state()
        fresh = (not force and st.get('latest') and not st.get('error')
                 and (st.get('checked_at') or 0) > time.time() - UPDATE_TTL)
        r = dict(update.blank(cur), **st) if fresh else update.check(current=cur)
        latest = r.get('latest') or ''
        newer = update.is_newer(cur, latest)
        if newer and not r.get('dmg_url'):
            try:
                r.update(update.release_details())
            except Exception as exc:
                r['error'] = update.describe_error(exc)
    except Exception as exc:  # never a traceback: the plugin parses one line
        r, latest, newer = dict(update.blank(cur), error=update.describe_error(exc)), '', False
    error = r.get('error') or ''
    _emit({'ok': 0 if error else 1, 'newer': int(newer), 'current': cur,
           'lib_version': __version__, 'latest': latest, 'tag': r.get('tag') or '',
           'title': ' '.join(str(r.get('title') or '').split())[:120],
           'dmg_url': r.get('dmg_url') or '', 'dmg_name': r.get('dmg_name') or '',
           'size': int(r.get('size') or 0), 'error': error})
    return 0


def _update_cli(args):
    current = ''
    if '--current' in args:
        i = args.index('--current')
        current = args[i + 1] if i + 1 < len(args) else ''
    return update_check(current, force='--force' in args)


def main(argv=None):
    args = sys.argv[1:] if argv is None else list(argv)
    # the plugin's modes skip argparse: it costs ~12 ms per launch
    if args[:1] == ['--cache']:
        return _cache_cli(args[1:], hard_limit=argv is None)
    if args[:1] == ['--to-resolve']:
        return to_resolve(args[1:])
    if args[:1] == ['--update-check']:
        return _update_cli(args[1:])

    import argparse
    ap = argparse.ArgumentParser(prog='slogmetaraw')
    ap.add_argument('paths', nargs='*')
    ap.add_argument('--json', action='store_true', help='print full JSON')
    ap.add_argument('--interval', type=float, default=1.0, help='seconds between sampled frames')
    ap.add_argument('--max-samples', type=int, default=FULL_SAMPLES, help='sampled frames per clip')
    ap.add_argument('--cache', action='store_true',
                    help='write the SLogMetaRaw plugin records and print their paths')
    ap.add_argument('--helper', action='store_true', help=argparse.SUPPRESS)
    ap.add_argument('--to-resolve', action='store_true',
                    help='legge i metadata di una clip e li scrive nel Media Pool di Resolve')
    a = ap.parse_args(args)
    if a.helper:
        return _helper(a.interval, a.max_samples)
    if a.to_resolve:
        return to_resolve(a.paths)
    if not a.paths:
        ap.error('servono uno o più percorsi (file o cartelle)')
    if a.cache:
        return cache_clips(a.paths, a.interval, a.max_samples)
    results = []
    status = 0
    for path in iter_clips(a.paths):
        t0 = time.time()
        try:
            r = read_clip(path, interval=a.interval, max_samples=a.max_samples)
        except DatalessError as e:
            print('SKIP', e, file=sys.stderr)
            continue
        except Exception as exc:  # a malformed clip must not stop the others
            print('ERROR %s: %s' % (path, exc), file=sys.stderr)
            status = 1
            continue
        r['elapsed_s'] = round(time.time() - t0, 3)
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
