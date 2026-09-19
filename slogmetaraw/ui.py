# SPDX-License-Identifier: GPL-3.0-or-later
"""S-Log MetaRaw window for DaVinci Resolve (Workspace > Scripts > S-Log MetaRaw)."""
import datetime
import os
import traceback

from . import __version__, extract, plugin_cache, resolve_io

SOURCES = ('Clip selezionate nel Media Pool', 'Bin corrente (con sottocartelle)', 'Tutto il Media Pool')
COLUMNS = ('Clip', 'Camera', 'Obiettivo', 'Focale', 'Diaframma', 'Shutter', 'ISO / EI',
           'WB', 'Color space', 'Data level', 'Stato', 'id')
EXPORT_DIR = os.path.expanduser('~/Documents/SLogMetaRaw')


def _row_values(clip, r):
    m, d = r['meta'], r['display']
    iso = str(m.get('iso') or '')
    if m.get('exposure_index') and m.get('exposure_index') != m.get('iso'):
        iso += ' / EI %s' % m['exposure_index']
    wb = d.get('white_balance_k') or '—'
    if m.get('tint'):
        wb += ' (%s)' % m['tint']
    status = 'letto'
    if r.get('changes'):
        status += ' · varia: ' + ', '.join(k.replace('_', ' ') for k in r['changes'])
    return [clip.GetName(), resolve_io._short_model(m.get('model')), m.get('lens') or '',
            d.get('focal_length_mm') or '', resolve_io.aperture_text(m), resolve_io.shutter_text(m),
            iso, wb, m.get('color_space') or '', m.get('luminance_code_range') or m.get('file_range') or '',
            status]


def main(resolve, fusion, bmd, selftest=False):
    ui = fusion.UIManager
    disp = bmd.UIDispatcher(ui)
    project = resolve.GetProjectManager().GetCurrentProject()
    mp = project.GetMediaPool()
    state = {'clips': {}, 'results': {}, 'items': {}}

    win = disp.AddWindow({
        'ID': 'SLogMetaRawWin',
        'WindowTitle': 'S-Log MetaRaw %s – metadata Sony nel Media Pool · Ivan Mazzone + Claude (@Ivan_94m)' % __version__,
        'Geometry': [100, 100, 1400, 800],
    }, ui.VGroup({'Spacing': 6}, [
        ui.HGroup({'Weight': 0}, [
            ui.Label({'Text': 'Origine:', 'Weight': 0}),
            ui.ComboBox({'ID': 'Source', 'Weight': 1}),
            ui.Button({'ID': 'Read', 'Text': '1 · Leggi metadata', 'Weight': 0}),
            ui.Button({'ID': 'Write', 'Text': '2 · Scrivi in Resolve', 'Weight': 0}),
            ui.Button({'ID': 'Export', 'Text': 'Esporta CSV (campi custom)', 'Weight': 0}),
        ]),
        ui.HGroup({'Weight': 0}, [
            ui.CheckBox({'ID': 'Overwrite', 'Text': 'Sovrascrivi i campi già compilati (consigliato: corregge anche i valori errati di Resolve, es. Camera Aperture FX6)', 'Checked': True}),
        ]),
        ui.HGroup({'Weight': 0}, [
            ui.CheckBox({'ID': 'SetICS', 'Text': 'Imposta anche Input Color Space (RCM) dai metadata – attenzione: dopo non si può riportare a "Project" da script', 'Checked': False}),
        ]),
        ui.HGroup({'Weight': 1}, [
            ui.Tree({'ID': 'Clips', 'Weight': 3, 'SortingEnabled': True,
                     'Events': {'CurrentItemChanged': True, 'ItemClicked': True}}),
            ui.Tree({'ID': 'Details', 'Weight': 2}),
        ]),
        ui.Label({'ID': 'Status', 'Weight': 0, 'Text': 'Scegli le clip e premi "Leggi metadata". I file originali non vengono mai modificati.'}),
    ]))
    itm = win.GetItems()
    for s in SOURCES:
        itm['Source'].AddItem(s)
    clips_tree = itm['Clips']
    clips_tree.ColumnCount = len(COLUMNS)
    clips_tree.SetHeaderLabels(list(COLUMNS))
    for i, w in enumerate((190, 70, 220, 60, 70, 70, 110, 80, 170, 120, 160, 0)):
        clips_tree.ColumnWidth[i] = w
    details = itm['Details']
    details.ColumnCount = 2
    details.SetHeaderLabels(['Campo (come Catalyst)', 'Valore'])
    details.ColumnWidth[0] = 260

    def status(text):
        itm['Status'].Text = text

    def gather():
        src = itm['Source'].CurrentIndex
        if src == 0:
            clips = mp.GetSelectedClips() or []
        elif src == 1:
            clips = list(resolve_io.iter_media_pool_clips(mp.GetCurrentFolder()))
        else:
            clips = list(resolve_io.iter_media_pool_clips(mp.GetRootFolder()))
        return [c for c in clips if resolve_io.clip_path(c)]

    def show_details(uid):
        details.Clear()
        r = state['results'].get(uid)
        if not r:
            return
        for title, rows in r['sections']:
            if not rows:
                continue
            parent = details.NewItem()
            parent.Text[0] = title
            parent.Text[1] = '%d campi' % len(rows)
            details.AddTopLevelItem(parent)
            for label, val in rows:
                child = details.NewItem()
                child.Text[0] = str(label)
                child.Text[1] = str(val)
                parent.AddChild(child)
            parent.Expanded = not title.startswith(('TAG NON', 'STABILIZZ'))
        if r.get('warnings'):
            parent = details.NewItem()
            parent.Text[0] = 'AVVISI'
            details.AddTopLevelItem(parent)
            for w in r['warnings']:
                child = details.NewItem()
                child.Text[0] = w
                parent.AddChild(child)
            parent.Expanded = True

    def on_read(ev):
        clips_tree.Clear()
        details.Clear()
        state['clips'].clear()
        state['results'].clear()
        clips = gather()
        if not clips:
            status('Nessuna clip MP4/MXF trovata per l\'origine scelta.')
            return
        ok = skipped = errors = 0
        for c in clips:
            uid = c.GetUniqueId()
            path = resolve_io.clip_path(c)
            row = clips_tree.NewItem()
            try:
                r = extract.read_clip(path)
                state['clips'][uid] = c
                state['results'][uid] = r
                plugin_cache.write_cache(r)
                vals = _row_values(c, r)
                ok += 1
            except extract.DatalessError:
                vals = [c.GetName()] + [''] * 9 + ['saltata: file su iCloud non scaricato']
                skipped += 1
            except Exception as exc:  # keep going on unreadable files
                vals = [c.GetName()] + [''] * 9 + ['errore: %s' % exc]
                errors += 1
                traceback.print_exc()
            for i, v in enumerate(vals + [uid]):
                row.Text[i] = str(v)
            clips_tree.AddTopLevelItem(row)
        status('Lette %d clip · saltate %d · errori %d. Seleziona una riga per vedere tutti i dati, poi "Scrivi in Resolve".'
               % (ok, skipped, errors))

    def on_select(ev):
        item = ev.get('item') if isinstance(ev, dict) else None
        if item is None:
            item = clips_tree.CurrentItem()
        if item is not None:
            show_details(item.Text[len(COLUMNS) - 1])

    def on_write(ev):
        if not state['results']:
            status('Prima premi "Leggi metadata".')
            return
        n = failed = 0
        cs = []
        for uid, r in state['results'].items():
            rep = resolve_io.apply_to_clip(state['clips'][uid], r,
                                           set_color_space=itm['SetICS'].Checked,
                                           overwrite=itm['Overwrite'].Checked)
            n += 1
            failed += len(rep['failed'])
            if rep['color_space']:
                cs.append(rep['color_space'])
        msg = 'Metadata scritti su %d clip.' % n
        if failed:
            msg += ' %d campi rifiutati da Resolve (vedi console).' % failed
        if cs:
            msg += ' Input Color Space impostato su %d clip.' % len(cs)
        status(msg)

    def on_export(ev):
        if not state['results']:
            status('Prima premi "Leggi metadata".')
            return
        os.makedirs(EXPORT_DIR, exist_ok=True)
        stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        name = '%s_%s.csv' % (project.GetName().replace('/', '-'), stamp)
        path = resolve_io.export_csv(list(state['results'].values()), os.path.join(EXPORT_DIR, name))
        status('CSV salvato: %s  →  in Resolve: File › Import › Metadata, con "crea campi custom" attivo.' % path)

    win.On.Read.Clicked = on_read
    win.On.Write.Clicked = on_write
    win.On.Export.Clicked = on_export
    win.On.Clips.CurrentItemChanged = on_select
    win.On.Clips.ItemClicked = on_select
    win.On.SLogMetaRawWin.Close = lambda ev: disp.ExitLoop()

    if mp.GetSelectedClips():
        itm['Source'].CurrentIndex = 0
    else:
        itm['Source'].CurrentIndex = 1
    win.Show()
    if selftest:  # used by automated checks: read the current bin, show first clip, close
        itm['Source'].CurrentIndex = 1
        on_read(None)
        first = clips_tree.TopLevelItem(0)
        if first is not None:
            show_details(first.Text[len(COLUMNS) - 1])
        info = {'status': itm['Status'].Text, 'rows': clips_tree.TopLevelItemCount(),
                'details': details.TopLevelItemCount()}
        win.Hide()
        return info
    disp.RunLoop()
    win.Hide()
