# SPDX-License-Identifier: GPL-3.0-or-later
"""S-Log MetaRaw window for DaVinci Resolve (Workspace > Scripts > S-Log MetaRaw).

Layout, top to bottom: buttons, options, live progress, clip list + details,
status bar with the clickable version. The window opens centered on the
DaVinci Resolve window (even in fullscreen), raised above it, and is resizable.

Long operations report live progress: clip parsing runs in a worker thread
(file I/O only — the Resolve API is never called from it), while a UI timer
drains the results and refreshes the window. Writing metadata runs in small
chunks on the timer itself, so every Resolve API call stays on the UI thread.
"""
import datetime
import json
import os
import select
import shutil
import subprocess
import sys
import threading
import time
import traceback
import webbrowser

from . import __version__, i18n, osx_utils, plugin_cache, resolve_io, update as upd

t = i18n.t

VERSION_STYLE = 'border: none; background: transparent;'
VERSION_STYLE_GREEN = 'color: rgb(46, 204, 113); border: none; background: transparent;'

SOURCES = ('Tutto il Media Pool', 'Clip selezionate nel Media Pool')
COLUMNS = ('Clip', 'Camera', 'Obiettivo', 'Focale', 'Diaframma', 'Shutter', 'ISO / EI',
           'WB', 'Color space', 'Data level', 'Stato', 'id')
EXPORT_DIR = os.path.expanduser('~/Documents/SLogMetaRaw')
TIMER_MS = 100     # UI refresh interval
WATCHDOG_MS = 250  # interval of the window-close watchdog (2 ticks confirm)
WRITE_CHUNK = 8    # SetMetadata calls per timer tick
CLIP_TIMEOUT = 15  # seconds per clip: longer means the read hangs and the clip is skipped
UI_LOG_PATH = os.path.expanduser('~/Library/Logs/SLogMetaRaw/ui.log')


def _ui_log(message):
    """Persist failures even when fuscript's console output is unavailable."""
    try:
        os.makedirs(os.path.dirname(UI_LOG_PATH), exist_ok=True)
        with open(UI_LOG_PATH, 'a', encoding='utf-8') as stream:
            stream.write('%s %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), message))
    except OSError:
        pass


def _log_exception(context):
    detail = traceback.format_exc()
    _ui_log('%s\n%s' % (context, detail))
    try:
        print(detail, file=sys.stderr)
    except Exception:
        pass


def _row_values(name, r):
    m, d = r['meta'], r['display']
    iso = str(m.get('iso') or '')
    if m.get('exposure_index') and m.get('exposure_index') != m.get('iso'):
        iso += ' / EI %s' % m['exposure_index']
    wb = d.get('white_balance_k') or '—'
    if m.get('tint'):
        wb += ' (%s)' % m['tint']
    status = t('letto')
    if r.get('changes'):
        status += t(' · varia: ') + ', '.join(k.replace('_', ' ') for k in r['changes'])
    return [name, resolve_io._short_model(m.get('model')), m.get('lens') or '',
            d.get('focal_length_mm') or '', resolve_io.aperture_text(m), resolve_io.shutter_text(m),
            iso, wb, m.get('color_space') or '',
            m.get('data_level') or m.get('luminance_code_range') or m.get('file_range') or '',
            status]


def _exit_with_resolve():
    """Resolve runs this script in a separate process. If Resolve quits (or crashes)
    while the window is open, that process is left orphaned and can get in the way of
    the next launch, so it follows its parent out."""
    parent = os.getppid()

    def watch():
        while True:
            time.sleep(2)
            if os.getppid() != parent:   # reparented to launchd: Resolve is gone
                os._exit(0)

    threading.Thread(target=watch, daemon=True).start()


def _reader_python():
    """Find an actual Python executable, including inside Resolve's host process."""
    executable = sys.executable or ''
    if executable and 'python' in os.path.basename(executable).lower():
        return executable
    # An in-process Workspace script reports Contents/MacOS/Resolve as its
    # executable. Launching that with -m opens another Resolve, not a reader.
    marker = '.app/Contents/'
    if marker in executable:
        contents = executable.split(marker, 1)[0] + marker
        bundled = os.path.join(contents, 'Resources', 'ResolvePython', 'ResolvePython')
        if os.path.isfile(bundled) and os.access(bundled, os.X_OK):
            return bundled
    python = shutil.which('python3')
    if python:
        return python
    raise RuntimeError('Python 3 executable not found for the metadata reader')


def _spawn_reader():
    """One persistent child process that parses clips (--helper mode).

    Parsing runs in a child so that a clip stuck on a dead volume can be killed:
    the scan must always be able to finish."""
    lib = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # ResolvePython runs in isolated mode via ResolvePython._pth, so it ignores
    # PYTHONPATH (and the working directory). Pass the installation path as data
    # and add it explicitly before running the helper module.
    bootstrap = ('import runpy, sys; sys.path.insert(0, sys.argv.pop(1)); '
                 'runpy.run_module("slogmetaraw", run_name="__main__")')
    return subprocess.Popen([_reader_python(), '-c', bootstrap, lib, '--helper'],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True, bufsize=1)


def _read_result(proc, deadline, cancelled=None):
    """One JSON result line from the reader, or None on timeout/death."""
    pending = getattr(proc, '_slog_pending', b'')
    while True:
        if cancelled is not None and cancelled.is_set():
            return None
        if b'\n' in pending:
            line, pending = pending.split(b'\n', 1)
            proc._slog_pending = pending
            try:
                return json.loads(line)
            except ValueError:
                continue     # stray non-JSON line: keep waiting
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        ready, _, _ = select.select([proc.stdout], [], [], min(remaining, 0.5))
        if ready:
            # readline() could block forever after select reports only part of
            # a line. Read available bytes so the per-clip deadline still holds.
            chunk = os.read(proc.stdout.fileno(), 65536)
            if not chunk:
                return None   # child died
            pending += chunk
            proc._slog_pending = pending
        # timeout not reached: loop with the updated deadline


def _stop_reader(proc):
    """Reap helper processes and close their pipes, including after a timeout."""
    if proc is None:
        return
    try:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        pass
    finally:
        for pipe in (proc.stdin, proc.stdout):
            if pipe is not None:
                try:
                    pipe.close()
                except OSError:
                    pass


def main(resolve, fusion, bmd, selftest=False):
    _exit_with_resolve()
    ui = fusion.UIManager
    disp = bmd.UIDispatcher(ui)
    project = resolve.GetProjectManager().GetCurrentProject()
    mp = project.GetMediaPool()

    state = {
        'clips': {},        # uid -> MediaPoolItem (used only while writing, on the UI thread)
        'results': {},      # uid -> result of the read
        'running': None,    # None | 'read' | 'write'
        'done': [],         # rows produced by the reader thread, drained by the timer
        'total': 0,
        'processed': 0,
        'finished': False,
        'summary': '',
        'had_errors': False,
        'write_queue': [],  # [(uid, clip, result)] still to be written
        'write_failed': 0,
        'write_broken': 0,
        'write_cs': [],
        'updating': False,      # update check in progress
        'update_done': None,    # result of the worker thread, applied by the timer
        'update_newer': False,  # a newer release is available: the chip is green
        'update_url': '',
        'update_latest': '',
    }
    done_idx = [0]  # number of 'done' entries already shown
    reader_cancelled = threading.Event()
    reader_thread = None
    closing = [False]
    watchdog_gone = [0]  # consecutive watchdog ticks with the native window gone

    # geometry: centered on the Resolve window, clamped to the main display
    b = osx_utils.resolve_window_bounds() or osx_utils.display_bounds() or (0, 0, 1920, 1080)
    db = osx_utils.display_bounds() or b
    w = max(680, min(1000, int(b[2] * 0.72)))
    h = max(400, min(620, int(b[3] * 0.68)))
    x = max(db[0], min(b[0] + (b[2] - w) // 2, db[0] + db[2] - w))
    y = max(db[1], min(b[1] + (b[3] - h) // 2, db[1] + db[3] - h))

    win = disp.AddWindow({
        'ID': 'SLogMetaRawWin',
        'WindowTitle': t('S-Log MetaRaw %s – metadata Sony nel Media Pool · Ivan Mazzone + Claude (@Ivan_94m)') % __version__,
        'Geometry': [x, y, w, h],
        # Deliberately no 'Events': {'Close': True}: on Resolve 21.1 (macOS)
        # that key intercepts the native title-bar close but never forwards it
        # to win.On.<ID>.Close, so the window can no longer be closed at all.
        # Without the key the native close still closes the window natively;
        # the watchdog timer then notices it and exits the dispatcher loop.
    }, ui.VGroup({'Spacing': 4}, [
        ui.HGroup({'Weight': 0}, [
            ui.ComboBox({'ID': 'Source', 'Weight': 1, 'MaximumSize': [240, 100],
                         'ToolTip': t('Quali clip leggere')}),
            ui.Button({'ID': 'Read', 'Text': t('1 · Leggi metadata'), 'Weight': 0}),
            ui.Button({'ID': 'Write', 'Text': t('2 · Scrivi in Resolve'), 'Weight': 0}),
            ui.Button({'ID': 'Export', 'Text': t('Esporta CSV'), 'Weight': 0,
                       'ToolTip': t('CSV con i campi custom, da importare in Resolve')}),
            # Do not call this widget Close: that name is reserved by the
            # window-level event namespace in Resolve's UIDispatcher.
            ui.Button({'ID': 'CloseButton', 'Text': t('Chiudi'), 'Weight': 0,
                       'ToolTip': t('Chiude la finestra S-Log MetaRaw')}),
        ]),
        ui.HGroup({'Weight': 0}, [
            ui.CheckBox({'ID': 'Tags', 'Weight': 0, 'Text': t('Tag per camera'),
                         'ToolTip': t('Aggiunge camera, gamma e primarie alle keyword di ogni clip (smart bin)')}),
            ui.CheckBox({'ID': 'Overwrite', 'Weight': 0, 'Checked': True, 'Text': t('Sovrascrivi metadata'),
                         'ToolTip': t('Se spento, riempie solo i campi vuoti e lascia i valori già presenti')}),
            ui.CheckBox({'ID': 'SetICS', 'Weight': 0, 'Text': t('Imposta anche Input Color Space'),
                         'ToolTip': t('RCM dai metadata. Attenzione: dopo non si può riportare a "Project" da script')}),
            ui.CheckBox({'ID': 'SetLevels', 'Weight': 0, 'Checked': True, 'Text': t('Correggi il Data Level'),
                         'ToolTip': t('Imposta Data Level = Full o Video in Attributi clip secondo la gamma di '
                                      'ripresa: è la correzione vera, vale per tutto il progetto')}),
        ]),
        ui.HGroup({'Weight': 0}, [
            ui.Label({'ID': 'Progress', 'Weight': 1, 'Text': ''}),
            ui.Label({'ID': 'Percent', 'Weight': 0, 'Text': '',
                      'Alignment': {'AlignRight': True}}),
        ]),
        ui.HGroup({'Weight': 1}, [
            ui.Tree({'ID': 'Clips', 'Weight': 3, 'SortingEnabled': True,
                     'Events': {'CurrentItemChanged': True, 'ItemClicked': True}}),
            ui.Tree({'ID': 'Details', 'Weight': 2}),
        ]),
        ui.HGroup({'Weight': 0}, [
            ui.Label({'ID': 'Status', 'Weight': 1, 'Text': ''}),
            ui.Label({'ID': 'UpdateIcon', 'Weight': 0, 'Text': ''}),
            ui.Button({'ID': 'Version', 'Text': 'v' + __version__, 'Weight': 0,
                       'StyleSheet': VERSION_STYLE,
                       'ToolTip': t('Controllo aggiornamenti: in arrivo')}),
        ]),
    ]))
    _ui_log('UI START source=%s pid=%s' % (__file__, os.getpid()))

    itm = win.GetItems()
    for s in SOURCES:
        itm['Source'].AddItem(t(s))
    itm['Source'].CurrentIndex = 0
    clips_tree = itm['Clips']
    clips_tree.ColumnCount = len(COLUMNS)
    clips_tree.SetHeaderLabels([t(c) for c in COLUMNS])
    for i, cw in enumerate((160, 60, 180, 55, 60, 60, 90, 70, 140, 100, 140, 0)):
        clips_tree.ColumnWidth[i] = cw
    details = itm['Details']
    details.ColumnCount = 2
    details.SetHeaderLabels([t('Campo (come Catalyst)'), t('Valore')])
    details.ColumnWidth[0] = 230

    timer = None

    def status(text):
        itm['Status'].Text = text

    def set_progress(text, pct):
        itm['Progress'].Text = text
        itm['Percent'].Text = ('%d%%' % pct) if pct is not None else ''

    def set_running(mode):
        state['running'] = mode
        busy = mode is not None or state['updating']
        for key in ('Source', 'Read', 'Write', 'Export', 'Version'):
            itm[key].Enabled = not busy

    def _stop_timer():
        try:
            timer.Stop()
        except Exception:
            pass

    def _hide_window(context):
        """Hide a Resolve window even when its native proxy is half-invalid."""
        try:
            hide = getattr(win, 'Hide', None)
            if callable(hide):
                hide()
        except Exception:
            _log_exception(context)
        # Resolve 21.x can leave the proxy visible after Hide() while the
        # dispatcher is unwinding. Setting the property is harmless when the
        # proxy is healthy and fixes that stale native wrapper case.
        try:
            win.Visible = False
        except Exception:
            pass

    def close_window(ev=None, native_gone=False):
        """Close the native window, then leave the dispatcher loop.

        The window Close event is delivered before the dispatcher returns; on
        builds that close the native window without any event the watchdog
        calls this with native_gone=True and the window is already off screen.
        Hiding here avoids leaving a stale native window visible while the
        reader thread is being stopped in the final cleanup block.
        """
        if closing[0]:
            return
        _ui_log('Close event received%s' % (' (native window already gone)' if native_gone else ''))
        closing[0] = True
        reader_cancelled.set()
        state['running'] = None
        state['updating'] = False
        _stop_timer()
        if not native_gone:
            _hide_window('Window hide on close')
        try:
            disp.ExitLoop()
        except Exception:
            _log_exception('Dispatcher exit on close')

    def _window_visible():
        """True/False from the window proxy, None when it cannot be read.

        None never counts as closed: a transient dispatcher hiccup must not
        close a healthy window."""
        try:
            return bool(win.Visible)
        except Exception:
            return None

    def _watchdog_tick():
        """Catch a native close that Resolve never forwarded as an event.

        Resolve 21.x builds can close the native window when the title-bar
        button is clicked without delivering win.On.<ID>.Close. Two
        consecutive ticks with the window gone confirm it really disappeared
        (a single stray read is ignored), then the shared cleanup runs."""
        try:
            if closing[0]:
                return
            if _window_visible() is False:
                watchdog_gone[0] += 1
            else:
                watchdog_gone[0] = 0
            if watchdog_gone[0] >= 2:
                _ui_log('Native window closed without a Close event (watchdog)')
                close_window(native_gone=True)
        except Exception:
            pass

    def guard(fn):
        """An exception inside a callback closes the script window: report it instead."""
        def wrapper(ev=None):
            try:
                return fn(ev)
            except Exception as exc:
                detail = traceback.format_exc()
                _ui_log('Callback: %s\n%s' % (fn.__name__, detail))
                status(t('Errore: %s  (dettagli nella console di Resolve)') % exc)
                try:
                    print(detail, file=sys.stderr)
                except Exception:
                    pass
        return wrapper

    # --- reading ------------------------------------------------------------

    def gather():
        src = itm['Source'].CurrentIndex
        if src == 0:
            clips = list(resolve_io.iter_media_pool_clips(mp.GetRootFolder()))
        else:
            clips = mp.GetSelectedClips() or []
        out = []
        for c in clips:
            path = resolve_io.clip_path(c)
            if path:
                out.append({'uid': c.GetUniqueId(), 'clip': c, 'name': c.GetName(), 'path': path})
        return out

    def read_worker(queue):
        ok = skipped = errors = slow = 0
        cache_error = None
        proc = None
        try:
            for entry in queue:
                if reader_cancelled.is_set():
                    break
                uid, name, path = entry['uid'], entry['name'], entry['path']
                row = {'uid': uid}
                msg = None
                if proc is None:
                    proc = _spawn_reader()
                try:
                    proc.stdin.write(path + '\n')
                    proc.stdin.flush()
                    msg = _read_result(proc, time.monotonic() + CLIP_TIMEOUT, reader_cancelled)
                except (BrokenPipeError, OSError):
                    msg = None
                if msg is None:
                    # Start the replacement only if another clip needs it.
                    _stop_reader(proc)
                    proc = None
                    if reader_cancelled.is_set():
                        break
                    row['values'] = [name] + [''] * 9 + [t('saltata: lettura troppo lenta (>%ds)') % CLIP_TIMEOUT]
                    slow += 1
                elif msg.get('ok'):
                    r = msg['result']
                    try:
                        plugin_cache.write_cache(r)
                    except OSError as exc:   # disk full or unwritable folder
                        cache_error = str(exc)
                    state['results'][uid] = r
                    row['values'] = _row_values(name, r)
                    ok += 1
                elif msg.get('kind') == 'dataless':
                    row['values'] = [name] + [''] * 9 + [t('saltata: file non presente in locale')]
                    skipped += 1
                else:
                    row['values'] = [name] + [''] * 9 + [t('errore: %s') % msg.get('error', 'sconosciuto')]
                    errors += 1
                state['done'].append(row)
                state['processed'] += 1
            msg_text = (t('Lette %d clip · saltate %d · lente %d · errori %d. Seleziona una riga per vedere tutti i dati, poi "Scrivi in Resolve".')
                        % (ok, skipped, slow, errors))
            if cache_error:
                msg_text += t('  ATTENZIONE: scheda per il plugin non salvata (%s).') % cache_error
            state['summary'] = msg_text
            state['had_errors'] = bool(errors or slow or cache_error)
        except Exception as exc:
            _log_exception('Metadata reader')
            state['summary'] = t('Errore: %s  (dettagli nella console di Resolve)') % exc
            state['had_errors'] = True
        finally:
            _stop_reader(proc)
            state['finished'] = True

    def _drain_read():
        d = state['done']
        while done_idx[0] < len(d):
            row = d[done_idx[0]]
            done_idx[0] += 1
            item = clips_tree.NewItem()
            for i, v in enumerate(row['values'] + [row['uid']]):
                item.Text[i] = str(v)
            clips_tree.AddTopLevelItem(item)
        total = state['total']
        n = state['processed']
        set_progress(t('Lettura metadata… %d/%d') % (n, total), int(n * 100 / total) if total else 100)
        if state['finished']:
            _finalize_read()

    def _finalize_read():
        _stop_timer()
        set_running(None)
        set_progress('', None)
        status(state['summary'])
        osx_utils.play_sound(not state['had_errors'])

    def on_read(ev, sync=False):
        nonlocal reader_thread
        clips_tree.Clear()
        details.Clear()
        state['clips'].clear()
        state['results'].clear()
        state['done'] = []
        done_idx[0] = 0
        state['processed'] = 0
        state['finished'] = False
        state['had_errors'] = False
        gathered = gather()
        if not gathered:
            status(t('Nessuna clip MP4/MXF trovata per l\'origine scelta.'))
            set_progress('', None)
            return
        state['clips'] = {g['uid']: g['clip'] for g in gathered}
        state['total'] = len(gathered)
        set_running('read')
        set_progress(t('Lettura metadata… %d/%d') % (0, len(gathered)), 0)
        if sync or not TIMER_OK:
            read_worker(gathered)
            _drain_read()
        else:
            timer.Start()
            reader_thread = threading.Thread(target=read_worker, args=(gathered,), daemon=True)
            reader_thread.start()

    # --- writing -------------------------------------------------------------

    def on_write(ev):
        if not state['results']:
            status(t('Prima premi "Leggi metadata".'))
            return
        state['write_queue'] = [(uid, state['clips'][uid], r)
                                for uid, r in state['results'].items() if uid in state['clips']]
        if not state['write_queue']:
            status(t('Nessuna clip letta da scrivere.'))
            return
        state['total'] = len(state['write_queue'])
        state['processed'] = 0
        state['write_failed'] = state['write_broken'] = 0
        state['write_cs'] = []
        state['write_levels'] = []
        state['finished'] = False
        set_running('write')
        set_progress(t('Scrittura in Resolve… %d/%d') % (0, state['total']), 0)
        if TIMER_OK:
            timer.Start()
        else:
            while not state['finished']:
                _pump_write()

    def _pump_write():
        for _ in range(WRITE_CHUNK):
            if not state['write_queue']:
                state['finished'] = True
                break
            uid, clip, r = state['write_queue'].pop(0)
            try:
                rep = resolve_io.apply_to_clip(clip, r,
                                               set_color_space=itm['SetICS'].Checked,
                                               overwrite=itm['Overwrite'].Checked,
                                               add_tags=itm['Tags'].Checked,
                                               set_data_level=itm['SetLevels'].Checked)
            except Exception:   # one problematic clip must not stop the others
                _log_exception('Metadata write')
                state['write_broken'] += 1
            else:
                state['write_failed'] += len(rep['failed'])
                if rep['color_space']:
                    state['write_cs'].append(rep['color_space'])
                if (rep.get('data_level') or {}).get('set'):
                    state['write_levels'].append(rep['data_level']['set'])
            state['processed'] += 1
        total = state['total']
        n = state['processed']
        set_progress(t('Scrittura in Resolve… %d/%d') % (n, total), int(n * 100 / total) if total else 100)
        if state['finished']:
            _finalize_write()

    def _finalize_write():
        _stop_timer()
        set_running(None)
        set_progress('', None)
        written = state['processed'] - state['write_broken']
        msg = t('Metadata scritti su %d clip.') % written
        if state['write_failed']:
            msg += t(' %d campi rifiutati da Resolve (vedi console).') % state['write_failed']
        if state['write_cs']:
            msg += t(' Input Color Space impostato su %d clip.') % len(state['write_cs'])
        if state['write_levels']:
            msg += t(' Data Level corretto su %d clip.') % len(state['write_levels'])
        if state['write_broken']:
            msg += t(' %d clip non scritte (vedi console).') % state['write_broken']
        status(msg)
        osx_utils.play_sound(state['write_broken'] == 0 and state['write_failed'] == 0)

    # --- details / export -----------------------------------------------------

    def show_details(uid):
        details.Clear()
        r = state['results'].get(uid)
        if not r:
            return
        for title, rows in r['sections']:
            if not rows:
                continue
            parent = details.NewItem()
            parent.Text[0] = t(title)
            parent.Text[1] = t('%d campi') % len(rows)
            details.AddTopLevelItem(parent)
            for label, val in rows:
                child = details.NewItem()
                child.Text[0] = str(t(label))
                child.Text[1] = str(val)
                parent.AddChild(child)
            parent.Expanded = not title.startswith(('TAG NON', 'STABILIZZ'))
        if r.get('warnings'):
            parent = details.NewItem()
            parent.Text[0] = t('AVVISI')
            details.AddTopLevelItem(parent)
            for w in r['warnings']:
                child = details.NewItem()
                child.Text[0] = str(t(w))
                parent.AddChild(child)
            parent.Expanded = True

    def on_select(ev):
        item = ev.get('item') if isinstance(ev, dict) else None
        if item is None:
            item = clips_tree.CurrentItem()
        if item is not None:
            show_details(item.Text[len(COLUMNS) - 1])

    def on_export(ev):
        if not state['results']:
            status('Prima premi "Leggi metadata".')
            return
        os.makedirs(EXPORT_DIR, exist_ok=True)
        stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        name = '%s_%s.csv' % (project.GetName().replace('/', '-'), stamp)
        path = resolve_io.export_csv(list(state['results'].values()), os.path.join(EXPORT_DIR, name))
        status(t('CSV salvato: %s  →  in Resolve: File › Import › Metadata, con "crea campi custom" attivo.') % path)

    # --- timer ------------------------------------------------------------------

    def on_timer(ev=None):
        who = ev.get('who') if isinstance(ev, dict) else None
        if who == 'WatchdogTimer':
            _watchdog_tick()
            return
        if state['running']:
            if state['running'] == 'read':
                _drain_read()
            else:
                _pump_write()
        elif state['updating'] and state['update_done'] is not None:
            _apply_update()

    TIMER_OK = False
    try:
        timer = ui.Timer({'ID': 'ProgressTimer', 'Interval': TIMER_MS})
        if timer is None:
            raise RuntimeError('UIManager Timer unavailable')
        # A standalone UITimer belongs to the dispatcher, not to the window's
        # child widgets. Registering win.On.ProgressTimer may silently succeed
        # even though no Timeout events are ever delivered there.
        disp.On.Timeout = guard(on_timer)
        TIMER_OK = True
    except Exception:
        timer = None

    # Watchdog: a slow always-on timer that keeps ticking while the loop is
    # idle too, to catch a native close that Resolve never reported as an
    # event. If it cannot be created the "Chiudi" button still closes the
    # window; a native close would just leave the loop running until Resolve
    # quits.
    WATCHDOG_OK = False
    watchdog = None
    try:
        watchdog = ui.Timer({'ID': 'WatchdogTimer', 'Interval': WATCHDOG_MS})
        if watchdog is None:
            raise RuntimeError('UIManager Timer unavailable')
        WATCHDOG_OK = True
    except Exception:
        watchdog = None

    # --- events ------------------------------------------------------------------

    win.On.Read.Clicked = guard(on_read)
    win.On.Write.Clicked = guard(on_write)
    win.On.Export.Clicked = guard(on_export)
    win.On.Clips.CurrentItemChanged = guard(on_select)
    win.On.Clips.ItemClicked = guard(on_select)
    # Two routes to close the window:
    # - the native title bar: on builds that forward the Close event this
    #   callback runs directly; on builds that only close the window natively
    #   (Resolve 21.x on macOS) the watchdog timer notices the window
    #   disappearing and calls the same cleanup;
    # - the "Chiudi" button: a deterministic fallback that always works.
    # Both routes share the same idempotent cleanup path.
    win.On.CloseButton.Clicked = close_window
    win.On.SLogMetaRawWin.Close = close_window

    # --- update check -----------------------------------------------------------

    def _update_worker():
        try:
            state['update_done'] = upd.check()
        except Exception as exc:
            _log_exception('Update check')
            result = upd.blank()
            result['error'] = str(exc)
            state['update_done'] = result

    def _apply_update():
        state['updating'] = False
        set_running(None)
        res = state['update_done'] or upd.blank()
        itm['UpdateIcon'].Text = ''
        if res.get('newer') and res.get('dmg_url'):
            state['update_newer'] = True
            state['update_url'] = res['dmg_url']
            state['update_latest'] = res['latest']
            itm['Version'].StyleSheet = VERSION_STYLE_GREEN
            itm['Version'].ToolTip = t('Disponibile la %s: clicca per scaricare') % res['latest']
            status(t('Disponibile la %s: clicca per scaricare') % res['latest'])
        elif res.get('error'):
            state['update_newer'] = False
            state['update_url'] = ''
            itm['Version'].StyleSheet = VERSION_STYLE
            itm['Version'].ToolTip = t('Controllo aggiornamenti: in arrivo')
            status(t('Controllo non riuscito: %s') % res['error'])
        else:
            state['update_newer'] = False
            state['update_url'] = ''
            itm['Version'].StyleSheet = VERSION_STYLE
            itm['Version'].ToolTip = t('Nessuna versione più recente (sei alla %s).') % res['current']
            status(t('Nessuna versione più recente (sei alla %s).') % res['current'])
        _stop_timer()

    def on_version(ev):
        if state['running'] or state['updating']:
            return
        if state['update_newer'] and state['update_url']:
            # the program only starts the download, nothing else
            try:
                webbrowser.open(state['update_url'])
                status(t('Download di S-Log MetaRaw %s avviato.') % state['update_latest'])
            except Exception:
                status(t('Controllo non riuscito: %s') % 'browser')
            return
        state['updating'] = True
        set_running(None)
        state['update_done'] = None
        itm['UpdateIcon'].Text = '🔍'
        itm['Version'].ToolTip = t('Controllo aggiornamenti…')
        if TIMER_OK:
            threading.Thread(target=_update_worker, daemon=True).start()
            timer.Start()
        else:
            _update_worker()
            _apply_update()

    win.On.Version.Clicked = guard(on_version)

    status(t('Scegli le clip e premi "Leggi metadata". I file originali non vengono mai modificati.'))

    win.Show()
    try:
        win.Raise()   # stay in front of DaVinci Resolve, windowed or fullscreen
    except Exception:
        pass

    if selftest:  # used by automated checks: read everything, show the first clip, close
        itm['Source'].CurrentIndex = 0
        on_read(None, sync=True)
        first = clips_tree.TopLevelItem(0)
        if first is not None:
            show_details(first.Text[len(COLUMNS) - 1])
        info = {'status': itm['Status'].Text, 'rows': clips_tree.TopLevelItemCount(),
                'details': details.TopLevelItemCount()}
        win.Hide()
        return info
    if WATCHDOG_OK:
        try:
            watchdog.Start()
        except Exception:
            pass
    try:
        disp.RunLoop()
    finally:
        reader_cancelled.set()
        _stop_timer()
        if watchdog is not None:
            try:
                watchdog.Stop()
            except Exception:
                pass
        if not closing[0]:   # already hidden by close_window when the close was explicit
            _hide_window('Window hide during cleanup')
        if reader_thread is not None:
            reader_thread.join(timeout=3)
