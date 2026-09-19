# SPDX-License-Identifier: GPL-3.0-or-later
"""Read every Sony metadata source of a clip into one structure.

read_clip(path) -> {
    'path', 'container', 'meta': {normalised key: value},
    'display': {normalised key: Catalyst-style string},
    'sections': [(title, [(label, display), ...]), ...],   # Catalyst-like view
    'rtmd': [decoded first-frame entries], 'changes': {...},
    'warnings': [...], 'bytes_read': int,
}
Nothing is written to the clip or next to it.
"""
import os
import re
import struct

from . import codec, mp4, mxf, nrt, rtmd

SF_DATALESS = 0x40000000  # macOS: only a placeholder on disk, the content lives in cloud storage

# values tracked across the clip to report what changes while recording
CHANGE_KEYS = ('iris_fnumber', 'focus_distance_m', 'focal_length_mm', 'shutter_speed',
               'shutter_angle', 'iso', 'exposure_index', 'master_gain_db', 'white_balance_k',
               'tint', 'nd_filter', 'awb_mode')
PARTIAL_READ = 2048  # bytes per sampled rtmd frame (lens + camera sets come first)


class DatalessError(Exception):
    pass


def find_sidecar(path):
    d, name = os.path.split(path)
    stem = os.path.splitext(name)[0]
    want = (stem + 'M01.XML').lower()
    try:
        for n in os.listdir(d or '.'):
            if n.lower() == want:
                return os.path.join(d, n)
    except OSError:
        pass
    return None


def _fps_value(s):
    if not s:
        return None
    m = re.match(r'([\d.]+)', str(s))
    return float(m.group(1)) if m else None


def _fmt_fps(x):
    return ('%.3f' % x).rstrip('0').rstrip('.') if x else ''


def _format_name(container, video_codec, width):
    vc = (video_codec or '').upper()
    intra = 'IP@' in vc or '422IP' in vc or 'INTRA' in vc
    hevc = vc.startswith('HEVC') or 'H.265' in vc
    try:
        w = int(width or 0)
    except ValueError:
        w = 0
    res = '4K' if w >= 3840 else ''
    if container == 'MXF':
        fam = 'XAVC Intra' if intra else ('XAVC H' if hevc else 'XAVC Long')
    else:
        fam = 'XAVC HS' if hevc else ('XAVC S-I' if intra else 'XAVC S')
    return (fam + ' ' + res).strip()


def _color_space(gamma, primaries):
    if gamma and '/' in gamma:
        return gamma
    if gamma in ('S-Log2', 'S-Log') and not primaries:
        return 'S-Gamut/' + gamma  # not recorded; Catalyst assumes S-Gamut too
    if gamma and primaries:
        return '%s/%s' % (primaries, gamma)
    return gamma or primaries or ''


def _sample_indices(n, fps, interval, max_samples):
    if n <= 0:
        return []
    step = max(1, int(round((fps or 25) * interval)))
    idx = list(range(0, n, step))
    if idx[-1] != n - 1:
        idx.append(n - 1)
    if len(idx) > max_samples:
        k = (len(idx) - 1) / (max_samples - 1)
        idx = sorted({idx[int(round(i * k))] for i in range(max_samples)})
    return idx


def _summarise_changes(series):
    changes = {}
    for key, vals in series.items():
        uniq = []
        for v in vals:
            if v not in uniq:
                uniq.append(v)
        if len(uniq) > 1:
            nums = [v for v in uniq if isinstance(v, (int, float))]
            changes[key] = {'first': vals[0], 'last': vals[-1], 'distinct': len(uniq),
                            'min': min(nums) if nums else None, 'max': max(nums) if nums else None}
    return changes


def _audio_info(track):
    e = track.sample_entry
    if len(e) < 36:
        return {}
    channels, bits = struct.unpack('>HH', e[24:28])
    rate = struct.unpack('>I', e[32:36])[0] >> 16
    names = {b'twos': 'Linear PCM', b'sowt': 'Linear PCM', b'lpcm': 'Linear PCM',
             b'ipcm': 'Linear PCM', b'mp4a': 'AAC'}
    return {'audio_codec': names.get(track.codec, track.codec.decode('latin1')),
            'audio_channels': channels, 'audio_bits': bits, 'audio_rate': rate}


def _read_mp4(f, out, interval, max_samples):
    m = mp4.MP4(f)
    meta = out['meta']
    xml = out.pop('_sidecar_xml', None) or m.meta_xml
    if xml:
        meta.update(nrt.parse(xml))
        out['nrt_source'] = 'embedded' if m.meta_xml else 'sidecar'
    if m.meta_items.get('Look Control data'):
        out['embedded_lut'] = m.meta_items['Look Control data']
    if m.meta_items.get('Lens profile'):
        meta['lens_profile_bytes'] = len(m.meta_items['Lens profile'])
    video = m.track(handler=b'vide')
    if video:
        info = codec.parse_sample_entry(video.codec, video.sample_entry)
        meta.update({'v_' + k: v for k, v in info.items()})
        meta['frames'] = video.sample_count()
        stts = video.tables.get(b'stts')
        if stts and video.timescale:
            delta = struct.unpack('>I', stts[12:16])[0]
            meta['fps'] = video.timescale / delta if delta else None
        if video.timescale and video.duration:
            secs = video.duration / video.timescale
            stsz = video.tables.get(b'stsz', b'')
            fixed, n = struct.unpack('>II', stsz[4:12]) if len(stsz) >= 12 else (0, 0)
            total = fixed * n if fixed else sum(struct.unpack('>%dI' % n, stsz[12:12 + 4 * n]))
            meta['duration_s'] = secs
            meta['bitrate_mbps'] = total * 8 / secs / 1e6 if secs else None
    audio = m.track(handler=b'soun')
    if audio:
        meta.update(_audio_info(audio))
    track = m.track(handler=b'meta', codec=b'rtmd')
    if not track:
        out['warnings'].append('Nessuna traccia rtmd: la camera non registra i dati di ripresa per-frame.')
        return
    n = track.sample_count()
    fps = meta.get('fps')
    wanted = _sample_indices(n, fps, interval, max_samples)
    offsets = track.sample_offsets(wanted)
    series = {k: [] for k in CHANGE_KEYS}
    for i in wanted:
        if i not in offsets:
            continue
        size = track.sample_size(i)
        buf = f.read_at(offsets[i], size if i == 0 else min(size, PARTIAL_READ))
        entries = rtmd.decode_mp4_sample(buf)
        if i == 0:
            out['rtmd'] = entries
        vals = rtmd.values(entries)
        for k in CHANGE_KEYS:
            if k in vals:
                series[k].append(vals[k])
    out['changes'] = _summarise_changes(series)
    out['rtmd_samples'] = {'total': n, 'read': len(offsets)}


def _read_mxf(f, out, interval, max_samples):
    meta = out['meta']
    xml = out.pop('_sidecar_xml', None) or mxf.find_nrt_xml(f)
    if xml:
        meta.update(nrt.parse(xml))
        out['nrt_source'] = 'sidecar' if out.get('sidecar') else 'embedded'
    fps = _fps_value(meta.get('format_fps')) or 25.0
    frames = meta.get('duration_frames') or 0
    meta['fps'] = fps
    meta['frames'] = frames
    if frames:
        meta['duration_s'] = frames / fps
        meta['bitrate_mbps'] = f.size * 8 / meta['duration_s'] / 1e6
    kind, sps = mxf.find_sps(f)
    if sps:
        try:
            info = codec.parse_avc_sps(sps) if kind == 'avc' else codec.parse_hevc_sps(sps)
            meta.update({'v_' + k: v for k, v in info.items()})
        except (IndexError, ValueError):
            pass
    ac = meta.get('audio_codec') or ''
    m = re.match(r'LPCM(\d+)', ac)
    if m:
        meta['audio_codec'] = 'Linear PCM'
        meta['audio_bits'] = int(m.group(1))
    first = mxf.find_rtmd(f, 0)
    if not first:
        out['warnings'].append('Metadata di acquisizione non trovati nell\'MXF.')
        return
    out['rtmd'] = rtmd.decode(first)
    series = {k: [] for k in CHANGE_KEYS}
    vals = rtmd.values(out['rtmd'])
    for k in CHANGE_KEYS:
        if k in vals:
            series[k].append(vals[k])
    secs = meta.get('duration_s') or 0
    n_windows = min(max(0, int(secs / max(interval, 1.0))), max_samples, 12)
    for w in range(1, n_windows + 1):
        pos = int(f.size * w / (n_windows + 1))
        payload = mxf.find_rtmd(f, pos, 3 * 1024 * 1024)
        if payload:
            v = rtmd.values(rtmd.decode(payload[:PARTIAL_READ]))
            for k in CHANGE_KEYS:
                if k in v:
                    series[k].append(v[k])
    out['changes'] = _summarise_changes(series)


def tc_to_frames(tc, fps):
    hh, mm, ss, ff = (int(x) for x in tc.split(':'))
    return ((hh * 60 + mm) * 60 + ss) * fps + ff


def frames_to_tc(n, fps):
    ff = n % fps
    s = n // fps
    return '%02d:%02d:%02d:%02d' % ((s // 3600) % 24, (s // 60) % 60, s % 60, ff)


def _normalise(out):
    """Merge rtmd first-frame values into meta and build display strings."""
    meta = out['meta']
    disp = out['display']
    tc_fps = int(_fps_value(meta.get('tc_fps')) or round(meta.get('fps') or 25))
    frames = meta.get('duration_frames') or meta.get('frames')
    if meta.get('start_tc') and frames:
        # End TC as Resolve/Catalyst show it (exclusive) and duration as timecode
        meta['end_tc'] = frames_to_tc(tc_to_frames(meta['start_tc'], tc_fps) + frames, tc_fps)
        meta['duration_tc'] = frames_to_tc(frames, tc_fps)
    for e in out.get('rtmd', []):
        if e['key'] and e['value'] is not None and e['key'] not in meta:
            meta[e['key']] = e['value']
            disp[e['key']] = e['display']
    attrs = meta.get('camera_attributes', '')
    m = re.search(r'Version\s*([\w.]+)', attrs)
    if m and not meta.get('firmware'):
        meta['firmware'] = m.group(1)
    if not meta.get('model') and attrs:
        meta['model'] = attrs.split()[0]
    meta.setdefault('manufacturer', 'Sony')
    cap = _fps_value(meta.get('capture_fps')) if isinstance(meta.get('capture_fps'), str) else None
    if isinstance(meta.get('capture_fps'), (list, tuple)):
        n, d = meta['capture_fps']
        cap = n / d if d else None
    meta['capture_fps_value'] = cap
    fps = meta.get('fps') or _fps_value(meta.get('format_fps'))
    meta['sq'] = bool(cap and fps and abs(cap - fps) > 0.01)
    meta['format_name'] = _format_name(out['container'], meta.get('video_codec'),
                                       meta.get('width') or meta.get('v_width'))
    gamma = meta.get('capture_gamma')
    prim = meta.get('color_primaries')
    meta['color_space'] = _color_space(gamma, prim)
    # plain gamma name (without gamut) for Resolve "Gamma Notes"
    cs = meta['color_space']
    if cs and '/' in cs:
        meta['gamma_name'] = cs.split('/')[-1]
        meta.setdefault('color_primaries', cs.split('/')[0])
    else:
        meta['gamma_name'] = gamma
    if 'white_balance_k' not in meta:
        out['warnings'].append('Temperatura colore non registrata dalla camera in questo file.')
    fr = meta.get('v_full_range', meta.get('v_colr_full_range'))
    meta['file_range'] = {True: 'Full', False: 'Video (legal)', None: 'non dichiarato (video)'}.get(fr)
    if out['container'] == 'MXF':
        meta['file_range'] = None


def _sections(out):
    m, d = out['meta'], out['display']

    def g(key, fmt=None):
        v = m.get(key)
        if v is None or v == '':
            return None
        if fmt:
            return fmt(v)
        return d.get(key, str(v))

    def rows(pairs):
        return [(label, val) for label, val in pairs if val not in (None, '')]

    sections = []
    sections.append(('MEDIA', rows([
        ('File name', os.path.basename(out['path'])),
        ('Folder', os.path.dirname(out['path'])),
        ('Format', g('format_name')),
        ('NRT metadata', {'sidecar': 'Sidecar XML', 'embedded': 'Embedded'}.get(out.get('nrt_source'))),
        ('LUT', g('lut_file')),
        ('Date created', g('creation_date')),
        ('Start time', g('start_tc')),
        ('End time', g('end_tc')),
        ('Length', g('duration_tc')),
        ('UMID', g('umid')),
    ])))
    sections.append(('SHOOTING INFORMATION', rows([
        ('Recording mode', g('recording_mode')),
        ('Frame rate', g('fps', lambda v: _fmt_fps(v) + ' fps')),
        ('Capture FPS', g('capture_fps')),
        ('Exposure index', g('exposure_index')),
        ('ISO sensitivity', g('iso')),
        ('Camera master gain adjustment', g('master_gain_db')),
        ('Shutter angle', g('shutter_angle')),
        ('Shutter speed', g('shutter_speed')),
        ('Iris f-number', g('iris_fnumber')),
        ('Lens zoom actual focal length', g('focal_length_mm')),
        ('Focus position from image plane', g('focus_distance_m')),
        ('ND filter wheel', g('nd_filter')),
        ('Monitoring descriptions', g('monitoring_descriptions')),
        ('Auto white balance mode', g('awb_mode')),
        ('Lighting preset', g('lighting_preset')),
        ('White balance', g('white_balance_k')),
        ('Tint Correction', g('tint')),
        ('Image stabilizer', g('image_stabilizer')),
    ])))
    sections.append(('VIDEO', rows([
        ('Codec', g('video_codec')),
        ('Profile and level', (m.get('v_profile') and '%s@L%s' % (m['v_profile'], m.get('v_level'))) or None),
        ('Color sampling', m.get('v_chroma') and 'YCbCr %s %sbit' % (m['v_chroma'], m.get('v_bit_depth'))),
        ('Color space', g('color_space')),
        ('Luminance code range', g('luminance_code_range')),
        ('Range dichiarato nel codec', g('file_range')),
        ('VUI primaries / transfer / matrix', m.get('v_vui_primaries') and '%s / %s / %s' % (
            m['v_vui_primaries'], m.get('v_vui_transfer'), m.get('v_vui_matrix'))),
        ('Bit rate', g('bitrate_mbps', lambda v: '%.0f Mbps' % v)),
        ('Frame size', m.get('width') and '%s x %s' % (m['width'], m.get('height'))),
        ('Aspect ratio', g('aspect_ratio')),
        ('Frame count', g('frames')),
        ('Field order', 'Interlaced' if m.get('v_interlaced') else 'Progressive'),
    ])))
    sections.append(('AUDIO', rows([
        ('Codec', g('audio_codec')),
        ('Sample rate', g('audio_rate', lambda v: '%g kHz' % (v / 1000))),
        ('Bit depth', g('audio_bits')),
        ('Channels', g('audio_channels')),
    ])))
    sections.append(('DEVICE', rows([
        ('Manufacturer', g('manufacturer')),
        ('Model name', g('model')),
        ('Device serial no.', g('serial')),
        ('Firmware', g('firmware')),
        ('Lens model name', g('lens')),
    ])))
    acq = [(e['label'], e['display']) for e in out.get('rtmd', [])
           if e['tag'] != '0xe000' and e['key'] and int(e['tag'], 16) < 0xe400]
    sections.append(('ACQUISITION METADATA', acq))
    stab = [(e['label'], e['display']) for e in out.get('rtmd', [])
            if e['key'] and int(e['tag'], 16) >= 0xe400]
    if stab:
        sections.append(('STABILIZZAZIONE / IMU / OTTICA (per Gyroflow, Catalyst Stabilize)', stab))
    if out.get('changes'):
        ch = []
        for k, c in out['changes'].items():
            label = rtmd_label(k)
            dv = lambda v: rtmd.display_value(k, v)  # noqa: E731
            txt = '%s → %s' % (dv(c['first']), dv(c['last']))
            if c['min'] is not None and c['min'] != c['max']:
                txt += '  (min %s, max %s)' % (dv(c['min']), dv(c['max']))
            ch.append((label, txt + '  [%d valori diversi]' % c['distinct']))
        sections.append(('VARIAZIONI DURANTE LA CLIP', ch))
    unknown = [(e['label'] + ' [%s]' % e['set'], e['raw']) for e in out.get('rtmd', []) if not e['key']]
    if unknown:
        sections.append(('TAG NON DECODIFICATI (raw)', unknown))
    return sections


def rtmd_label(key):
    for spec in rtmd.TAGS.values():
        if spec[0] == key:
            return spec[1]
    return key


def read_clip(path, interval=1.0, max_samples=120, allow_dataless=False):
    path = os.path.abspath(path)
    st = os.stat(path)
    if getattr(st, 'st_flags', 0) & SF_DATALESS and not allow_dataless:
        raise DatalessError('File non presente in locale, solo segnaposto: %s' % path)
    out = {'path': path, 'meta': {}, 'display': {}, 'rtmd': [], 'changes': {}, 'warnings': []}
    side = find_sidecar(path)
    if side:
        out['sidecar'] = side
        with open(side, 'rb') as fh:
            out['_sidecar_xml'] = fh.read()
    with mp4.CountingFile(path) as f:
        head = f.read_at(0, 16)
        if mxf.is_mxf(head):
            out['container'] = 'MXF'
            _read_mxf(f, out, interval, max_samples)
        else:
            out['container'] = 'MP4'
            _read_mp4(f, out, interval, max_samples)
        out['bytes_read'] = f.bytes_read
        out['file_size'] = f.size
    out.pop('_sidecar_xml', None)
    _normalise(out)
    out['sections'] = _sections(out)
    return out


def is_sony_clip(path):
    ext = os.path.splitext(path)[1].lower()
    return ext in ('.mp4', '.mxf') and (find_sidecar(path) is not None or ext == '.mp4')
