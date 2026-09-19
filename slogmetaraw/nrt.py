# SPDX-License-Identifier: GPL-3.0-or-later
"""Parser for Sony NonRealTimeMeta XML (sidecar *M01.XML or embedded copy)."""
import xml.etree.ElementTree as ET


def _local(tag):
    return tag.rsplit('}', 1)[-1]


def _find(root, name):
    for el in root.iter():
        if _local(el.tag) == name:
            return el
    return None


def _findall(root, name):
    return [el for el in root.iter() if _local(el.tag) == name]


def ltc_to_tc(value):
    """NRT LTC value 'FFSSMMHH' (BCD, with flag bits) -> 'HH:MM:SS:FF'."""
    if not value or len(value) != 8:
        return None
    ff, ss, mm, hh = (int(value[i:i + 2], 16) for i in (0, 2, 4, 6))
    ff, ss, mm, hh = ff & 0x3F, ss & 0x7F, mm & 0x7F, hh & 0x3F
    return '%02x:%02x:%02x:%02x' % (hh, mm, ss, ff)


def parse(xml_bytes):
    # the copy embedded in MP4 files is NUL-terminated
    end = xml_bytes.rfind(b'</NonRealTimeMeta>')
    if end >= 0:
        xml_bytes = xml_bytes[:end + len(b'</NonRealTimeMeta>')]
    root = ET.fromstring(xml_bytes)
    out = {'nrt_version': root.tag.split('}')[0].strip('{').rsplit(':', 1)[-1],
           'last_update': root.get('lastUpdate')}
    el = _find(root, 'TargetMaterial')
    if el is not None:
        out['umid'] = el.get('umidRef')
    el = _find(root, 'Duration')
    if el is not None:
        out['duration_frames'] = int(el.get('value'))
    el = _find(root, 'LtcChangeTable')
    if el is not None:
        out['tc_fps'] = el.get('tcFps')
        out['tc_half_step'] = el.get('halfStep')
        changes = _findall(el, 'LtcChange')
        if changes:
            out['start_tc'] = ltc_to_tc(changes[0].get('value'))
            ends = [c for c in changes if c.get('status') == 'end']
            if ends:
                out['end_tc'] = ltc_to_tc(ends[-1].get('value'))
    el = _find(root, 'CreationDate')
    if el is not None:
        out['creation_date'] = el.get('value')
    el = _find(root, 'VideoFrame')
    if el is not None:
        out['video_codec'] = el.get('videoCodec')
        out['capture_fps'] = el.get('captureFps')
        out['format_fps'] = el.get('formatFps')
    el = _find(root, 'VideoLayout')
    if el is not None:
        out['width'] = el.get('pixel')
        out['height'] = el.get('numOfVerticalLine')
        out['aspect_ratio'] = el.get('aspectRatio')
        if el.get('flip'):
            out['flip'] = el.get('flip')
    el = _find(root, 'AudioFormat')
    if el is not None:
        out['audio_channels'] = el.get('numOfChannel')
        codecs = sorted({p.get('audioCodec') for p in _findall(el, 'AudioRecPort') if p.get('audioCodec')})
        out['audio_codec'] = ', '.join(codecs)
    el = _find(root, 'SubStream')
    if el is not None:
        out['proxy_codec'] = el.get('codec')
    el = _find(root, 'Device')
    if el is not None:
        out['manufacturer'] = el.get('manufacturer')
        out['model'] = el.get('modelName')
        serial = el.get('serialNo')
        if serial and serial != '4294967295':  # 0xFFFFFFFF = not provided
            out['serial'] = serial
        for elem in _findall(el, 'Element'):
            if elem.get('software'):
                out['firmware'] = elem.get('software')
    el = _find(root, 'Lens')
    if el is not None:
        out['lens'] = el.get('modelName')
    el = _find(root, 'RecordingMode')
    if el is not None:
        out['recording_mode'] = el.get('type')
        out['cache_rec'] = el.get('cacheRec')
    for item in _findall(root, 'Item'):
        name, value = item.get('name'), item.get('value')
        if name == 'CaptureGammaEquation':
            out['xml_gamma'] = value
        elif name == 'CaptureColorPrimaries':
            out['xml_primaries'] = value
        elif name == 'CodingEquations':
            out['xml_coding'] = value
    tables = {}
    for ct in _findall(root, 'ChangeTable'):
        ev = _find(ct, 'Event')
        tables[ct.get('name')] = ev.get('status') if ev is not None else None
    if tables:
        out['change_tables'] = tables
    for rel in _findall(root, 'RelatedTo'):
        if rel.get('rel') == 'LUT':
            out['lut_file'] = rel.get('file')
    for pkt in _findall(root, 'KlvPacket'):
        v = pkt.get('lengthValue') or ''
        try:
            txt = bytes.fromhex(v)[1:].decode('ascii')
            out.setdefault('klv_markers', []).append(txt)
        except ValueError:
            pass
    return out
