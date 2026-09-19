# SPDX-License-Identifier: GPL-3.0-or-later
"""Sony XAVC MXF support: acquisition metadata in ST 436 ANC packets + NRT XML.

Only small windows of the file are read: the head (first frame), the tail
(embedded NRT XML) and a few windows spread across the file to detect
values that change during the clip.
"""
import re
import struct

ANC_KEY = bytes.fromhex('060e2b34010201010d01030117')  # ST 436 ANC data element
SONY_DID, SONY_SDID = 0x43, 0x05
WINDOW = 4 * 1024 * 1024


def is_mxf(head):
    return head[:4] == b'\x06\x0e\x2b\x34'


def _anc_payload(buf, i):
    """Reassemble Sony acquisition metadata from the ANC KLV at buf[i]."""
    l = buf[i + 16]
    if l & 0x80:
        n = l & 0x7F
        length = int.from_bytes(buf[i + 17:i + 17 + n], 'big')
        vs = i + 17 + n
    else:
        length, vs = l, i + 17
    v = buf[vs:vs + length]
    if len(v) < length or len(v) < 2:
        return None
    count = struct.unpack('>H', v[:2])[0]
    q = 2
    parts = []
    for _ in range(count):
        if q + 14 > len(v):
            break
        q += 6  # line number, wrapping type, sample coding, sample count
        n, size = struct.unpack('>II', v[q:q + 8])
        q += 8
        arr = v[q:q + n * size]
        q += n * size
        # arr: DID, SDID, DC, then UDW (first UDW byte is a sequence counter)
        if len(arr) >= 4 and arr[0] == SONY_DID and arr[1] == SONY_SDID:
            parts.append(arr[4:3 + arr[2]])
    return b''.join(parts) if parts else None


CHUNK = 256 * 1024


def find_rtmd(f, pos, window=WINDOW):
    """Find the first Sony ANC metadata payload at or after file offset pos.

    Reads in small chunks and stops as soon as one ANC element is complete
    (it sits at the start of every frame's content package).
    """
    buf = b''
    base = pos
    start = 0
    while len(buf) < window and base + len(buf) < f.size:
        buf += f.read_at(base + len(buf), CHUNK)
        while True:
            i = buf.find(ANC_KEY, start)
            if i < 0:
                start = max(0, len(buf) - 16)
                break
            if i + 32 > len(buf):
                break
            l = buf[i + 16]
            n = l & 0x7F if l & 0x80 else 0
            length = int.from_bytes(buf[i + 17:i + 17 + n], 'big') if n else l
            if i + 17 + n + length > len(buf):
                break  # need more data
            payload = _anc_payload(buf, i)
            if payload:
                return payload
            start = i + 16
    return None


SPS_RE = re.compile(rb'\x00\x00\x01(?:([\x07\x27\x47\x67])|(\x42\x01))')


def find_sps(f, window=8 * 1024 * 1024):
    """Return (codec, SPS NAL bytes) of the first picture, searching by start code."""
    buf = b''
    while len(buf) < window and len(buf) < f.size:
        buf += f.read_at(len(buf), CHUNK)
        m = SPS_RE.search(buf)
        if m:
            j = buf.find(b'\x00\x00\x01', m.start() + 4)
            if j > 0:
                return ('avc' if m.group(1) else 'hevc'), buf[m.start() + 3:j]
    return None, None


def find_nrt_xml(f):
    """Embedded NonRealTimeMeta XML: look in the head and the tail of the file."""
    for pos in (0, max(0, f.size - WINDOW)):
        buf = f.read_at(pos, WINDOW)
        i = buf.find(b'<NonRealTimeMeta')
        if i >= 0:
            j = buf.find(b'</NonRealTimeMeta>', i)
            if j > 0:
                k = buf.rfind(b'<?xml', 0, i)
                return buf[k if k >= 0 and i - k < 200 else i:j + len(b'</NonRealTimeMeta>')]
    return None
