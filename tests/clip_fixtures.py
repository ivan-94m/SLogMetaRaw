# SPDX-License-Identifier: GPL-3.0-or-later
"""Synthetic Sony clips for the reader tests: XAVC MP4 (rtmd track) and XAVC MXF (SMPTE ST 377-1).

Each frame records white balance 3000 + frame index, so first and last values
identify exactly which frames were read.
"""
import struct

UL = b'\x06\x0e\x2b\x34'
# SPS of a real FX6 clip (H.264 High 4:2:2, 1920x1080 10 bit): codec parameters only
SPS = bytes.fromhex('677a1029b6d420223319c6632321011198ce331918210256b93d7d7e4fe33f11'
                    'f19e08b88c5443c0780227e2701e30202024000003000400000300ca10')
GAMMA_SLOG3_CINE = UL + bytes.fromhex('0401010d0e060401') + bytes.fromhex('01010605')
PRIMARIES_SGAMUT3_CINE = UL + bytes.fromhex('0401010d0e060401') + bytes.fromhex('01030105')

NRT_XML = '''<?xml version="1.0" encoding="UTF-8"?>
<NonRealTimeMeta xmlns="urn:schemas-professionalDisc:nonRealTimeMeta:ver.2.20" lastUpdate="2026-01-01T10:00:00+01:00">
<Duration value="{frames}"/>
<LtcChangeTable tcFps="25" halfStep="false"><LtcChange frameCount="0" value="00000010" status="increment"/></LtcChangeTable>
<VideoFormat><VideoFrame videoCodec="AVC_1920_1080_H422IP@L41" captureFps="25p" formatFps="25p"/>
<VideoLayout pixel="1920" numOfVerticalLine="1080" aspectRatio="16:9"/></VideoFormat>
<Device manufacturer="Sony" modelName="ILME-FX6V" serialNo="1234567"/>
<AcquisitionRecord><Group name="CameraUnitMetadataSet">
<Item name="CaptureGammaEquation" value="s-log3-cine"/><Item name="CaptureColorPrimaries" value="s-gamut3-cine"/>
</Group></AcquisitionRecord>
</NonRealTimeMeta>
'''


def ber(n):
    if n < 0x80:
        return bytes([n])
    return b'\x83' + n.to_bytes(3, 'big')


def klv(key, value):
    return key + ber(len(value)) + value


def rtmd_payload(frame):
    """Camera and lens sets as Sony writes them (RDD 18 local tags)."""
    def pack(tail, tags):
        body = b''.join(struct.pack('>HH', tag, len(v)) + v for tag, v in tags)
        return klv(UL + bytes.fromhex('02530101') + bytes.fromhex(tail), body)
    lens = pack('0c02010101010000', [(0x8000, struct.pack('>H', 45000))])
    camera = pack('0c02010102010000', [
        (0x3210, GAMMA_SLOG3_CINE), (0x3219, PRIMARIES_SGAMUT3_CINE),
        (0x810b, struct.pack('>H', 800)), (0x8115, struct.pack('>H', 3200)),
        (0x810e, struct.pack('>H', 3000 + frame)), (0x811f, struct.pack('>h', 0)),
        (0x8120, b'\x02')])
    return lens + camera


# --- MP4 ---------------------------------------------------------------------------

def _box(typ, payload):
    return struct.pack('>I4s', 8 + len(payload), typ) + payload


def _full(typ, payload):
    return _box(typ, b'\0\0\0\0' + payload)


def build_mp4(path, frames=250, free=256 * 1024):
    """XAVC-like MP4: ftyp, free, mdat with one rtmd sample per frame, moov, NRT meta.

    Returns the byte range of the samples in mdat."""
    samples = [struct.pack('>H', 0x1c) + b'\0' * 26 + rtmd_payload(i) for i in range(frames)]
    ftyp = _box(b'ftyp', b'XAVC\0\0\0\0XAVCmp42iso2') + _box(b'free', b'\0' * free)
    data_start = len(ftyp) + 8
    offsets, pos = [], data_start
    for s in samples:
        offsets.append(pos)
        pos += len(s)
    mdat = _box(b'mdat', b''.join(samples))
    stbl = _box(b'stbl',
                _full(b'stsd', struct.pack('>I', 1) + _box(b'rtmd', b'\0' * 8))
                + _full(b'stts', struct.pack('>III', 1, frames, 1))
                + _full(b'stsc', struct.pack('>IIII', 1, 1, 1, 1))
                + _full(b'stsz', struct.pack('>II', 0, frames) + b''.join(struct.pack('>I', len(s)) for s in samples))
                + _full(b'stco', struct.pack('>I', frames) + b''.join(struct.pack('>I', o) for o in offsets)))
    mdia = _box(b'mdia', _full(b'mdhd', struct.pack('>IIIIHH', 0, 0, 25, frames, 0, 0))
                + _full(b'hdlr', b'\0\0\0\0meta' + b'\0' * 13)
                + _box(b'minf', stbl))
    moov = _box(b'moov', _box(b'trak', mdia))
    meta = _box(b'meta', b'\0\0\0\0' + _full(b'hdlr', b'\0\0\0\0nrtm' + b'\0' * 13)
                + _full(b'xml ', NRT_XML.format(frames=frames).encode() + b'\0'))
    with open(path, 'wb') as fh:
        fh.write(ftyp + mdat + moov + meta)
    return data_start, data_start + sum(len(s) for s in samples)


# --- MXF ---------------------------------------------------------------------------

PARTITION = UL + bytes.fromhex('020501010d01020101')        # + kind + status + 00
FILL = UL + bytes.fromhex('010101020301021001000000')
PRIMER = UL + bytes.fromhex('020501010d01020101050100')
CDCI = UL + bytes.fromhex('025301010d01010101012800')
DARK = UL + bytes.fromhex('010101050e0600000000000000')[:12]   # unregistered key: dark metadata
INDEX = UL + bytes.fromhex('025301010d01020101100100')
SYSTEM = UL + bytes.fromhex('020501010d01030104010100')
PICTURE = UL + bytes.fromhex('010201010d01030115010500')
SOUND = UL + bytes.fromhex('010201010d010301160803')     # + channel
ANC = UL + bytes.fromhex('010201010d01030117010201')
OP1A = UL + bytes.fromhex('040101010d01020101010900')


def _partition(kind, this, footer, hbc, ibc, index_sid):
    value = struct.pack('>HHIQQQQQIQI', 1, 3, 512, this, 0, footer, hbc, ibc, index_sid, 0, 2)
    value += OP1A + struct.pack('>II', 0, 16)
    return klv(PARTITION + bytes([kind, 4, 0]), value)


def _fill_to(data, boundary):
    """data followed by a fill KLV (4-byte BER length) ending on a multiple of boundary."""
    n = (-len(data) - 20) % boundary
    return data + FILL + b'\x83' + n.to_bytes(3, 'big') + b'\0' * n


def _anc(payload):
    packets = [payload[i:i + 250] for i in range(0, len(payload), 250)]
    out = struct.pack('>H', len(packets))
    for n, chunk in enumerate(packets):
        arr = bytes([0x43, 0x05, len(chunk) + 1, n]) + chunk
        out += struct.pack('>HBBH', 9, 1, 4, len(arr)) + struct.pack('>II', len(arr), 1) + arr
    return klv(ANC, out)


def _index_segment(first, offsets, eubc):
    tags = [(0x3C0A, b'\x11' * 16), (0x3F0B, struct.pack('>ii', 25, 1)),
            (0x3F0C, struct.pack('>Q', first)), (0x3F0D, struct.pack('>Q', len(offsets))),
            (0x3F05, struct.pack('>I', eubc)), (0x3F06, struct.pack('>I', 1)),
            (0x3F07, struct.pack('>I', 2)), (0x3F08, b'\0')]
    if offsets:
        entries = b''.join(struct.pack('>bbBQ', 0, 0, 0xC0, off) for off in offsets)
        tags.append((0x3F0A, struct.pack('>II', len(offsets), 11) + entries))
    return klv(INDEX, b''.join(struct.pack('>HH', t, len(v)) + v for t, v in tags))


def build_mxf(path, frames=40, picture=100 * 1024, header_fill=5 * 1024 * 1024, index='vbe',
              anc=True, xml_gamma=None, header_junk=b''):
    """XAVC-like MXF with the essence after header_fill bytes of header metadata.

    index: 'vbe' (entry array, two segments), 'cbe' (edit unit byte count) or None;
    header_junk goes into a dark set before the XML. Returns the first package offset."""
    xml = NRT_XML.format(frames=frames)
    if xml_gamma:
        xml = xml.replace('s-log3-cine', xml_gamma)
    cdci = struct.pack('>HHI', 0x3301, 4, 10) + struct.pack('>HHI', 0x3304, 4, 64) \
        + struct.pack('>HHI', 0x3305, 4, 940) + struct.pack('>HHI', 0x3306, 4, 897)
    header = klv(PRIMER, struct.pack('>II', 0, 18)) + klv(CDCI, cdci)
    if header_junk:
        header += klv(DARK, header_junk)
    header += klv(DARK, xml.encode())
    header += klv(FILL, b'\0' * header_fill)
    header = _fill_to(header, 512)

    packages = []
    for i in range(frames):
        size = picture if index == 'cbe' else picture + (i % 7) * 1000
        cp = _fill_to(klv(SYSTEM, b'\0' * 57), 512)
        cp += klv(PICTURE, (b'\0\0\0\x01\x09\x10\0\0\0\x01' + SPS + b'\0\0\0\x01\x68\xee' + b'\0' * size)[:size])
        cp += b''.join(klv(SOUND + bytes([ch]), b'\0' * 5760) for ch in range(2))
        if anc:
            cp += _anc(rtmd_payload(i))
        packages.append(_fill_to(cp, 512) if index == 'cbe' else cp)
    if index == 'cbe':
        assert len(set(map(len, packages))) == 1
    offsets, pos = [], 0
    for cp in packages:
        offsets.append(pos)
        pos += len(cp)
    if index == 'vbe':
        half = frames // 2
        idx = _index_segment(half, offsets[half:], 0) + _index_segment(0, offsets[:half], 0)
    elif index == 'cbe':
        idx = _index_segment(0, [], len(packages[0]))
    else:
        idx = b''
    idx = _fill_to(idx, 512) if idx else b''

    head_len = len(_partition(2, 0, 0, 0, 0, 0))
    lead = _fill_to(b'\0' * head_len, 512)[head_len:]           # KAG fill after the pack
    essence_start = head_len + len(lead) + len(header) + len(idx)
    footer_pos = essence_start + pos
    first = _partition(2, 0, footer_pos, len(header), len(idx), 1 if idx else 0)
    assert len(first) == head_len
    with open(path, 'wb') as fh:
        fh.write(first + lead + header + idx + b''.join(packages)
                 + _partition(4, footer_pos, footer_pos, 0, 0, 0))
    return essence_start
