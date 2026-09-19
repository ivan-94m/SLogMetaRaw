# SPDX-License-Identifier: GPL-3.0-or-later
"""Per-clip JSON records read by the SLogMetaRaw OpenFX plugin.

The plugin knows its source file path (Resolve's kOfxImageEffectPropSrcFilePath)
and looks for ~/Library/Application Support/SLogMetaRaw/cache/<fnv1a64(path)>.json.
The script writes these records while registering metadata in Resolve; if one is
missing the plugin runs `ResolvePython -m slogmetaraw --cache <path>` itself.
The file name hash (FNV-1a 64 of the UTF-8 path) is duplicated in the plugin.
"""
import json
import os

from . import camera, resolve_io

CACHE_DIR = os.path.expanduser('~/Library/Application Support/SLogMetaRaw/cache')
VERSION = 2


def fnv1a64(text):
    h = 0xcbf29ce484222325
    for b in text.encode('utf-8'):
        h ^= b
        h = (h * 0x100000001b3) & 0xFFFFFFFFFFFFFFFF
    return '%016x' % h


def cache_path(clip_path):
    return os.path.join(CACHE_DIR, fnv1a64(clip_path) + '.json')


def _join(*parts):
    return ' · '.join(str(p) for p in parts if p not in (None, ''))


def build_record(r):
    """Flat record with the values the plugin shows and uses (strings and numbers only)."""
    m, d = r['meta'], r['display']
    k, tint, ei, estimated = camera.shot_values(m)
    try:
        cam_gamut, cam_gamma = camera.camera_space(m)
        supported = 1
    except camera.NotSupported:
        cam_gamut, cam_gamma, supported = '', '', 0
    iso = m.get('iso')

    focal = d.get('focal_length_mm') or ''
    if focal and d.get('focal_length_35mm'):
        focal += ' (35mm eq. %s)' % d['focal_length_35mm']
    shutter = resolve_io.shutter_text(m)
    if shutter and isinstance(m.get('shutter_angle'), (int, float)):
        shutter += ' (%g°)' % round(m['shutter_angle'], 1)
    exposure = _join('ISO %s' % iso if iso else '',
                     'EI %s' % m['exposure_index'] if m.get('exposure_index') and m.get('exposure_index') != iso else '',
                     'gain %s' % d['master_gain_db'] if m.get('master_gain_db') else '')
    wb = _join('%dK' % k + (' stimato' if estimated else ''), 'Tint %g' % tint,
               m.get('awb_mode'), m.get('lighting_preset'))
    fps = m.get('capture_fps') or ''
    if m.get('sq'):
        fps = 'S&Q %gp -> %sp' % (m.get('capture_fps_value') or 0, ('%g' % m['fps']) if m.get('fps') else '?')
    labels = {'iris_fnumber': 'diaframma', 'focus_distance_m': 'fuoco', 'focal_length_mm': 'focale',
              'shutter_speed': 'shutter', 'shutter_angle': 'shutter', 'iso': 'ISO', 'exposure_index': 'EI',
              'master_gain_db': 'gain', 'white_balance_k': 'WB', 'tint': 'tint', 'nd_filter': 'ND',
              'awb_mode': 'modo WB'}
    changes = ', '.join(dict.fromkeys(labels.get(key, key) for key in (r.get('changes') or {})))
    stab = {'enabled': 'attivo', 'disabled': 'spento'}.get(m.get('image_stabilizer'), m.get('image_stabilizer'))
    model = m.get('model') or ''
    short = resolve_io._short_model(model)

    return {
        'version': VERSION,
        'path': r['path'],
        'supported': supported,
        'shot_temp': k,
        'shot_tint': tint,
        'shot_ei': ei,
        'wb_estimated': 1 if estimated else 0,
        'cam_space': camera.SPACE_CODE.get(cam_gamut, -1),
        'cam_gamma': camera.GAMMA_CODE.get(cam_gamma, -1),
        'model': m.get('model') or '',
        'color_space': m.get('color_space') or '',
        # shown by the plugin (read-only fields)
        'camera_name': ('%s %s' % (m.get('manufacturer') or 'Sony', model)).strip()
                       + (' (%s)' % short if short and short != model else ''),
        'lens': m.get('lens') or '—',
        'focal': focal or '—',
        'iris': ('f/%.1f' % m['iris_fnumber']) if m.get('iris_fnumber') else '—',
        'focus': resolve_io.distance_text(m) or '—',
        'shutter': shutter or '—',
        'exposure': exposure or '—',
        'white_balance': wb,
        'color': _join(m.get('color_space'), 'Data level %s' % (m.get('luminance_code_range') or m.get('file_range'))
                       if (m.get('luminance_code_range') or m.get('file_range')) else ''),
        'fps': _join(fps, 'varia: %s' % changes if changes else '') or '—',
        'nd_stab': _join('ND %s' % m['nd_filter'] if m.get('nd_filter') else '',
                         'stabilizzatore %s' % stab if stab else '') or '—',
        'lut': m.get('monitoring_descriptions') or m.get('lut_file') or '—',
        'file': _join(os.path.basename(r['path']), m.get('format_name'), 'SN %s' % m['serial'] if m.get('serial') else ''),
    }


def write_cache(r):
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = cache_path(r['path'])
    tmp = path + '.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8') as fh:
            json.dump(build_record(r), fh, ensure_ascii=False)
        os.replace(tmp, path)  # atomic: the plugin never sees a half-written file
    except OSError:            # disk full or read-only: leave no half-written file behind
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return path
