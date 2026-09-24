# SPDX-License-Identifier: GPL-3.0-or-later
"""Map S-Log MetaRaw results to DaVinci Resolve media pool metadata.

Standard Resolve metadata fields are written with MediaPoolItem.SetMetadata.
Resolve's API cannot create custom metadata fields, so everything else goes
into a [S-Log MetaRaw] block inside "Camera Notes" (user text outside the block is
kept) and into a CSV/ALE that Resolve can import with "create custom fields".
"""
import csv
import io
import os

from . import datalevel

NOTES_START = '[S-Log MetaRaw]'
NOTES_END = '[/S-Log MetaRaw]'
VIDEO_EXTS = ('.mp4', '.mxf')

# Resolve Input Color Space names verified on 21.1 (SetClipProperty accepts them)
RESOLVE_COLOR_SPACES = {
    'S-Gamut3.Cine/S-Log3': 'S-Gamut3.Cine/S-Log3',
    'S-Gamut3/S-Log3': 'S-Gamut3/S-Log3',
    'S-Gamut/S-Log2': 'S-Gamut/S-Log2',
    'S-Gamut/S-Log': 'S-Gamut/S-Log',
    'ITU-R BT.2100 HLG': 'Rec.2100 HLG',
    'HLG Live (S-Log3 OOTF)': 'Rec.2100 HLG',
    'HLG Mild (S-Log3 OOTF)': 'Rec.2100 HLG',
    'S-Cinetone': 'Rec.709 (Scene)',
    'ITU-R BT.709-5': 'Rec.709 (Scene)',
}


# Resolve's per-clip "Data Level" attribute: 'Auto', 'Full' or 'Video'. It is the
# scale Resolve uses when it decodes the clip into its 32-bit float pipeline, and
# it is applied before the node graph, so it decides what an OpenFX node receives.
DATA_LEVEL_PROPERTY = 'Data Level'


def read_data_level(clip):
    """The clip's Data Level as 'Auto' / 'Full' / 'Video', or None if unreadable."""
    try:
        v = clip.GetClipProperty(DATA_LEVEL_PROPERTY)
    except Exception:
        return None
    if isinstance(v, dict):
        v = v.get(DATA_LEVEL_PROPERTY)
    v = (v or '').strip().lower()
    return {'auto': datalevel.AUTO, 'full': datalevel.FULL, 'video': datalevel.VIDEO}.get(v)


def sync_data_level(clip, r, apply_fix=False):
    """Read (and optionally correct) this clip's Data Level in Resolve.

    Resolve's "Auto" is documented as a per-codec guess and the resolved value is
    not exposed by any API, so leaving it on Auto means the node cannot know which
    scale its input is on. Setting it explicitly is the real fix: it corrects the
    decode for the whole project — CSTs, RCM and scopes included — not just for
    the node. It is fully reversible, SetClipProperty accepts 'Auto' again.
    """
    meta = r['meta']
    host = read_data_level(clip)
    meta['resolve_data_level'] = host or datalevel.AUTO
    required = meta.get('level_required')
    report = {'read': host, 'required': required, 'set': None}
    if apply_fix and required and host is not None and host != required:
        ok = False
        try:
            ok = bool(clip.SetClipProperty(DATA_LEVEL_PROPERTY, required))
        except Exception:
            ok = False
        report['set'] = required if ok else 'FAILED ' + required
        if ok:
            meta['resolve_data_level'] = required
    d = datalevel.decide(meta, meta['resolve_data_level'])
    r['data_level'] = d
    meta['level_note'] = d['note']
    meta['data_level'] = datalevel.summary(meta, meta['resolve_data_level'])
    if r.get('sections'):   # the details panel must show the final state
        from .extract import _sections
        r['sections'] = _sections(r)
    return report


def _fmt_num(v, fmt='%g'):
    return fmt % v if isinstance(v, (int, float)) else str(v)


def _short_model(model):
    """ILME-FX30 -> FX30, ILCE-7SM3 -> A7SM3, ILCE-6300 -> A6300."""
    if not model:
        return ''
    m = model.split('-', 1)[-1] if '-' in model else model
    if model.upper().startswith('ILCE-'):
        m = 'A' + m
    return m


def shutter_text(meta):
    s = meta.get('shutter_speed')
    if isinstance(s, (list, tuple)) and s[1]:
        return '1/%d' % s[1] if s[0] == 1 else '%gs' % (s[0] / s[1])
    return ''


def aperture_text(meta):
    f = meta.get('iris_fnumber')
    return 'F%.1f' % f if isinstance(f, (int, float)) and 0.5 < f < 64 else ''


def distance_text(meta):
    d = meta.get('focus_distance_m')
    if not isinstance(d, (int, float)):
        return ''
    return '∞' if d >= 1000 else '%.2f m' % d


def summary_line(r):
    m = r['meta']
    parts = [_short_model(m.get('model'))]
    if m.get('lens'):
        parts.append(m['lens'])
    if m.get('focal_length_mm'):
        parts.append('%gmm' % round(m['focal_length_mm'], 1))
    if aperture_text(m):
        parts.append('f/%.1f' % m['iris_fnumber'])
    if shutter_text(m):
        ang = m.get('shutter_angle')
        parts.append(shutter_text(m) + (' (%g°)' % ang if isinstance(ang, (int, float)) else ''))
    iso = m.get('iso')
    ei = m.get('exposure_index')
    if iso:
        parts.append('ISO %s' % iso + (' / EI %s' % ei if ei and ei != iso else ''))
    if m.get('white_balance_k'):
        parts.append('%dK' % m['white_balance_k'] + (' tint %s' % m['tint'] if m.get('tint') else ''))
    if m.get('color_space'):
        parts.append(m['color_space'])
    if m.get('sq'):
        parts.append('S&Q %gp' % m['capture_fps_value'])
    return ' · '.join(p for p in parts if p)


def notes_block(r):
    m = r['meta']
    lines = [summary_line(r)]
    extra = []
    for label, key in (('Data level', 'data_level'), ('Luminance code range', 'luminance_code_range'),
                       ('Range codec', 'file_range'),
                       ('WB', 'awb_mode'), ('Lighting preset', 'lighting_preset'),
                       ('AE', 'ae_mode'), ('AF', 'af_area'), ('Gain', 'master_gain_db'),
                       ('Stabilizzatore', 'image_stabilizer'), ('LUT', 'monitoring_descriptions'),
                       ('35mm eq.', 'focal_length_35mm'), ('Registrata', 'recording_time')):
        v = r['display'].get(key) or m.get(key)
        if v not in (None, ''):
            extra.append('%s: %s' % (label, v))
    if extra:
        lines.append(' · '.join(extra))
    if r.get('changes'):
        from .rtmd import display_value
        ch = ['%s %s→%s' % (k.replace('_', ' '), display_value(k, c['first']), display_value(k, c['last']))
              for k, c in r['changes'].items()]
        lines.append('Varia durante la clip: ' + '; '.join(ch))
    for w in r.get('warnings', []):
        lines.append('! ' + w)
    return NOTES_START + '\n' + '\n'.join(lines) + '\n' + NOTES_END


def merge_notes(existing, block):
    existing = existing or ''
    i = existing.find(NOTES_START)
    j = existing.find(NOTES_END)
    if i >= 0 and j > i:
        before = existing[:i].rstrip()
        after = existing[j + len(NOTES_END):].strip()
    else:
        before, after = existing.strip(), ''
    return '\n\n'.join(p for p in (before, block, after) if p)


def keywords(r):
    m = r['meta']
    kw = [_short_model(m.get('model')), m.get('gamma_name') or '', m.get('color_primaries') or '']
    if m.get('sq'):
        kw.append('S&Q')
    return [k for k in kw if k]


def merge_keywords(existing, new):
    cur = [k.strip() for k in (existing or '').split(',') if k.strip()]
    for k in new:
        if k not in cur:
            cur.append(k)
    return ','.join(cur)


def build_fields(r):
    """Resolve standard metadata fields -> string values (empty values omitted)."""
    m, d = r['meta'], r['display']
    cap = m.get('capture_fps_value') or m.get('fps')
    sensor = ''
    if m.get('sensor_width_um') and m.get('sensor_height_um'):
        sensor = '%.2f x %.2f mm' % (m['sensor_width_um'] / 1000, m['sensor_height_um'] / 1000)
    lens_notes = []
    if m.get('focal_length_35mm'):
        lens_notes.append('35mm eq. %s' % d.get('focal_length_35mm'))
    if m.get('breathing_comp_enabled') is not None:
        lens_notes.append('Breathing comp. %s' % ('On' if m['breathing_comp_enabled'] else 'Off'))
    fields = {
        'Camera Manufacturer': m.get('manufacturer') or 'Sony',
        'Camera Type': m.get('model') or '',
        'Camera TC Type': m.get('model') or '',   # Resolve itself puts the model here for FX6
        'Camera Serial #': m.get('serial') or '',
        'Camera Firmware': m.get('firmware') or '',
        'Camera FPS': '%.3f' % cap if cap else '',
        'Shutter Type': 'Speed and Angle' if m.get('shutter_angle') is not None else (
            'Speed' if shutter_text(m) else ''),
        'Shutter Angle': '%.1f' % m['shutter_angle'] if isinstance(m.get('shutter_angle'), (int, float)) else '',
        'Shutter Speed': shutter_text(m),
        'Exposure Mode': m.get('ae_mode') or '',
        'ISO': str(m['iso']) if m.get('iso') else '',
        'White Point (Kelvin)': str(m['white_balance_k']) if m.get('white_balance_k') else '',
        'White Balance Tint': str(m['tint']) if m.get('tint') is not None else '',
        'Mon Color Space': m.get('monitoring_descriptions') or '',
        'Monitor LUT': '1' if m.get('monitoring_descriptions') else '',
        'LUT Used': m.get('lut_file') or '',
        'Lens Type': m.get('lens') or '',
        'Lens Number': m.get('lens_attributes') or '',
        'Lens Notes': ' · '.join(lens_notes),
        'Camera Aperture Type': 'F-Stop' if aperture_text(m) else '',
        'Camera Aperture': aperture_text(m),
        'Focal Point (mm)': _fmt_num(round(m['focal_length_mm'], 1)) if m.get('focal_length_mm') else '',
        'Distance': distance_text(m),
        'ND Filter': m.get('nd_filter') or '',
        'Codec Bitrate': '%.0f Mbps' % m['bitrate_mbps'] if m.get('bitrate_mbps') else '',
        'Sensor Area Captured': sensor,
        'PAR Notes': '1',
        'Aspect Ratio Notes': m.get('aspect_ratio') or '',
        'Gamma Notes': m.get('gamma_name') or '',
        'Color Space Notes': m.get('color_primaries') or '',
        'Date Recorded': (m.get('recording_time') or m.get('creation_date') or '')[:10],
    }
    return {k: v for k, v in fields.items() if v not in (None, '')}


def apply_to_clip(clip, r, set_color_space=False, overwrite=True, add_tags=True,
                  set_data_level=False):
    """Write metadata to a MediaPoolItem. Returns dict with written/failed keys."""
    # first, so that the notes, the cache record and the node all see the final state
    data_level = sync_data_level(clip, r, apply_fix=set_data_level)
    fields = build_fields(r)
    existing = clip.GetMetadata() or {}
    if not overwrite:
        fields = {k: v for k, v in fields.items() if not existing.get(k)}
    fields['Camera Notes'] = merge_notes(existing.get('Camera Notes'), notes_block(r))
    if add_tags:
        fields['Keywords'] = merge_keywords(existing.get('Keywords'), keywords(r))
    report = {'written': [], 'failed': [], 'color_space': None, 'data_level': data_level}
    if clip.SetMetadata(fields):
        report['written'] = list(fields)
    else:  # find the offending keys
        for k, v in fields.items():
            (report['written'] if clip.SetMetadata({k: v}) else report['failed']).append(k)
    tp = {'SLogMetaRaw.version': '1'}
    for k, v in r['meta'].items():
        if isinstance(v, (str, int, float, bool)) and len(str(v)) < 200:
            tp['SLogMetaRaw.' + k] = str(v)
    clip.SetThirdPartyMetadata(tp)
    try:  # record for the SLogMetaRaw plugin
        from .plugin_cache import write_cache
        report['cache'] = write_cache(r)
    except OSError as exc:
        report['cache_error'] = str(exc)
    if set_color_space:
        target = RESOLVE_COLOR_SPACES.get(r['meta'].get('color_space') or '') or \
            RESOLVE_COLOR_SPACES.get(r['meta'].get('capture_gamma') or '')
        if target and clip.GetClipProperty('Input Color Space') != target:
            ok = clip.SetClipProperty('Input Color Space', target)
            report['color_space'] = target if ok else 'FAILED ' + target
    return report


# --- export for custom fields ---------------------------------------------

CUSTOM_COLUMNS = (
    ('Sony EI', 'exposure_index'), ('Sony ISO', 'iso'), ('Sony Gain', 'master_gain_db'),
    ('Sony WB Mode', 'awb_mode'), ('Sony Lighting Preset', 'lighting_preset'),
    ('Sony Tint', 'tint'), ('Sony AE Mode', 'ae_mode'), ('Sony AF', 'af_area'),
    ('Sony Focal 35mm', 'focal_length_35mm'), ('Sony Focus Distance', 'focus_distance_m'),
    ('Sony Color Space', 'color_space'), ('Sony Gamma', 'capture_gamma'),
    ('Sony Luminance Code Range', 'luminance_code_range'), ('Sony Codec Range', 'file_range'),
    ('Sony Data Level', 'data_level'), ('Sony Data Level Required', 'level_required'),
    ('Sony Data Level Declared', 'level_declared'), ('Resolve Data Level', 'resolve_data_level'),
    ('Sony Stabilizer', 'image_stabilizer'), ('Sony Monitoring LUT', 'monitoring_descriptions'),
    ('Sony Recording Mode', 'recording_mode'), ('Sony Capture FPS', 'capture_fps'),
    ('Sony Recording Time', 'recording_time'), ('Sony Format', 'format_name'),
)


def export_csv(results, path):
    """CSV in Resolve's own metadata format (UTF-16), importable via
    File > Import > Metadata; unknown 'Sony …' columns become custom fields."""
    std = sorted({k for r in results for k in build_fields(r)})
    header = ['File Name', 'Clip Directory'] + std + ['Camera Notes', 'Keywords'] + \
        [c for c, _ in CUSTOM_COLUMNS]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator='\n')
    w.writerow(header)
    for r in results:
        f = build_fields(r)
        row = [os.path.basename(r['path']), os.path.dirname(r['path'])]
        row += [f.get(k, '') for k in std]
        row += [notes_block(r), ','.join(keywords(r))]
        row += [r['display'].get(key) or str(r['meta'].get(key, '') or '') for _, key in CUSTOM_COLUMNS]
        w.writerow(row)
    with open(path, 'w', encoding='utf-16') as fh:
        fh.write(buf.getvalue())
    return path


def iter_media_pool_clips(folder, recursive=True):
    for c in folder.GetClipList() or []:
        yield c
    if recursive:
        for sub in folder.GetSubFolderList() or []:
            yield from iter_media_pool_clips(sub, True)


def clip_path(clip):
    p = clip.GetClipProperty('File Path') or ''
    return p if p.lower().endswith(VIDEO_EXTS) else ''
