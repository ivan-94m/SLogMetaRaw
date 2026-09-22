# SPDX-License-Identifier: GPL-3.0-or-later
"""Sony XAVC MXF support: acquisition metadata in ST 436 ANC packets + NRT XML.

Only small windows of the file are read: the head (first frame), the tail
(embedded NRT XML and the Random Index Pack) and a few windows spread across the
file to detect values that change during the clip.

WHERE to read those windows is taken from the file's own structure rather than
guessed. An MXF states, in its partition packs, exactly how many bytes of header
metadata and index table sit before its essence, and its Random Index Pack lists
every partition's offset. Scanning blindly from byte 0 works on a short HD clip
and stops working as soon as the index table grows: a 97 minute 25p clip carries
~145800 index entries, which on its own pushes the first essence past a 4 MiB
window. All those fields are 64 bit, so nothing here has a 4 GB ceiling.
"""
import re
import struct

ANC_KEY = bytes.fromhex('060e2b34010201010d01030117')  # ST 436 ANC data element
SONY_DID, SONY_SDID = 0x43, 0x05
WINDOW = 4 * 1024 * 1024
WINDOW_MAX = 64 * 1024 * 1024    # ceiling for the adaptive scan, see scan_window()
TAIL = 128 * 1024                # enough for the Random Index Pack

# ST 377-1 partition packs. Byte 13 is header (0x02) / body (0x03) / footer (0x04),
# byte 14 the status, so only the first 13 bytes identify the family.
PARTITION_PREFIX = bytes.fromhex('060e2b34020501010d0102010102')[:13]
RIP_KEY = bytes.fromhex('060e2b34020501010d01020101110100')
# major, minor, KAGSize, ThisPartition, PreviousPartition, FooterPartition,
# HeaderByteCount, IndexByteCount, IndexSID, BodyOffset, BodySID
PARTITION_FIELDS = '>HHIQQQQQIQI'
PARTITION_FIXED = struct.calcsize(PARTITION_FIELDS)   # 64


def is_mxf(head):
    return head[:4] == b'\x06\x0e\x2b\x34'


def _ber(buf, i):
    """(length, offset after the length) of a BER-encoded length at buf[i]."""
    b = buf[i]
    if b & 0x80:
        n = b & 0x7F
        if n == 0 or i + 1 + n > len(buf):
            return None, i + 1
        return int.from_bytes(buf[i + 1:i + 1 + n], 'big'), i + 1 + n
    return b, i + 1


def partition_at(f, pos):
    """The ST 377-1 partition pack at `pos`, or None if there is not one there.

    'essence' is the offset of the first essence KLV of this partition: the end of
    the pack plus the header metadata and index table it declares. That is the
    number the scan needs, and it costs one short read to get.
    """
    buf = f.read_at(pos, 1024)
    if len(buf) < 17 or buf[:13] != PARTITION_PREFIX:
        return None
    length, vs = _ber(buf, 16)
    if not length or vs + PARTITION_FIXED > len(buf):
        return None
    v = struct.unpack(PARTITION_FIELDS, buf[vs:vs + PARTITION_FIXED])
    out = dict(zip(('major', 'minor', 'kag', 'this', 'prev', 'footer',
                    'header_bytes', 'index_bytes', 'index_sid', 'body_offset',
                    'body_sid'), v))
    out['kind'] = {0x02: 'header', 0x03: 'body', 0x04: 'footer'}.get(buf[13], '?')
    out['essence'] = pos + vs + length + out['header_bytes'] + out['index_bytes']
    return out


def partition_offsets(f):
    """Every partition's offset, from the Random Index Pack in the file's tail.

    The RIP is the last KLV in a closed and complete MXF and lists (BodySID,
    ByteOffset) for each partition, all 64 bit. Returns [] when there is no RIP,
    which is normal for a file still being written.
    """
    pos = max(0, f.size - TAIL)
    buf = f.read_at(pos, TAIL)
    i = buf.rfind(RIP_KEY)
    if i < 0:
        return []
    length, vs = _ber(buf, i + 16)
    if not length or length < 4:
        return []
    pairs = buf[vs:vs + length - 4]
    out = []
    for q in range(0, len(pairs) - 11, 12):
        _sid, off = struct.unpack('>IQ', pairs[q:q + 12])
        if 0 <= off < f.size:
            out.append(off)
    return sorted(set(out))


def scan_window(f, duration_s=None):
    """How far to scan for one ANC element, from the clip's own bitrate.

    A content package is System, Picture, Sound, then Data - so the ANC element
    sits behind a whole picture element, which at 4K long-GOP is the anchor frame
    of the GOP and can be several megabytes on its own. Two seconds of essence
    covers that with room to spare, and the ceiling keeps a pathological file from
    turning the scan into a full read.
    """
    if not duration_s or duration_s <= 0:
        return WINDOW
    per_second = f.size / duration_s
    return int(min(max(2.0 * per_second, WINDOW), WINDOW_MAX))


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


# An element that begins inside the window but runs past it is not "no element":
# reading a little more is what tells the two apart. Bounded so a corrupt length
# cannot turn the scan into a full read of the file.
STRADDLE_MAX = 8 * 1024 * 1024


def find_rtmd(f, pos, window=WINDOW):
    """Find the first Sony ANC metadata payload at or after file offset pos.

    Reads in small chunks and stops as soon as one Sony ANC element is complete.
    An ANC element that is not Sony's - a timecode one, say - is skipped rather
    than ending the search, and an element straddling the end of the window is
    completed instead of being silently dropped.
    """
    buf = b''
    base = pos
    start = 0
    limit = window
    while len(buf) < limit and base + len(buf) < f.size:
        buf += f.read_at(base + len(buf), CHUNK)
        while True:
            i = buf.find(ANC_KEY, start)
            if i < 0:
                start = max(0, len(buf) - 16)
                break
            if i + 32 > len(buf):
                limit = min(max(limit, len(buf) + CHUNK), window + STRADDLE_MAX)
                break
            length, vs = _ber(buf, i + 16)
            if length is None:
                start = i + 16
                continue
            if vs + length > len(buf):
                # keep reading until this one element is whole, then stop growing
                limit = min(max(limit, vs + length), window + STRADDLE_MAX)
                break
            payload = _anc_payload(buf, i)
            if payload:
                return payload
            start = i + 16
    return None


def find_acquisition(f, duration_s=None, extra=()):
    """(payload, offset, tried): the first Sony acquisition payload in the file.

    Looks where the file says its essence is, not where a fixed window hopes it
    is. In order: the first partition's declared essence offset, then every
    partition the Random Index Pack lists, then whatever extra offsets the caller
    wants tried (the fractional windows used for change detection), then byte 0 as
    the last resort for a file whose structure would not parse.

    `tried` is the list of offsets attempted, so a failure can say how hard it
    looked instead of just saying no.
    """
    window = scan_window(f, duration_s)
    spots = []
    head = partition_at(f, 0)
    if head:
        spots.append(head['essence'])
    for off in partition_offsets(f):
        part = partition_at(f, off)
        spots.append(part['essence'] if part else off)
    spots.extend(extra)
    spots.append(0)
    tried = []
    for spot in spots:
        if spot is None or not 0 <= spot < f.size or spot in tried:
            continue
        tried.append(spot)
        payload = find_rtmd(f, spot, window)
        if payload:
            return payload, spot, tried
    return None, None, tried


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


# --- picture essence descriptor: the only place an MXF states its code range ---
# SMPTE ST 377-1 CDCI/RGBA essence descriptors carry the reference levels as local
# tags in the header metadata. Sony XAVC MXF writes them, and they are the only
# declaration of range an MXF has (there is no colr box and no VUI to trust here).
CDCI_KEY = bytes.fromhex('060e2b34025301010d01010101012800')  # CDCIEssenceDescriptor
RGBA_KEY = bytes.fromhex('060e2b34025301010d01010101012900')  # RGBAEssenceDescriptor
# local tag -> key, as registered in the SMPTE dictionary
PICTURE_TAGS = {
    0x3301: 'mxf_component_depth',
    0x3302: 'mxf_horizontal_subsampling',
    0x3304: 'mxf_black_ref',
    0x3305: 'mxf_white_ref',
    0x3306: 'mxf_color_range',
    0x3308: 'mxf_vertical_subsampling',
}


def _local_set(buf, i, length):
    """Decode an MXF local set (2-byte tag, 2-byte length, value) into {tag: bytes}."""
    out = {}
    end = min(i + length, len(buf))
    while i + 4 <= end:
        tag = int.from_bytes(buf[i:i + 2], 'big')
        size = int.from_bytes(buf[i + 2:i + 4], 'big')
        i += 4
        if i + size > end:
            break
        out[tag] = buf[i:i + size]
        i += size
    return out


def find_picture_levels(f, window=WINDOW):
    """{mxf_black_ref, mxf_white_ref, mxf_color_range, mxf_component_depth, ...}.

    Reads only the head of the file, where the header metadata lives - as much of
    it as the header partition says there is, so a long clip whose metadata runs
    past the default window still declares its range. Returns an empty dict when
    no picture descriptor is found or it states no reference levels.
    """
    head = partition_at(f, 0)
    if head and head['header_bytes']:
        window = max(window, min(head['header_bytes'] + 64 * 1024, WINDOW_MAX))
    buf = f.read_at(0, min(window, f.size))
    for key in (CDCI_KEY, RGBA_KEY):
        start = 0
        while True:
            i = buf.find(key, start)
            if i < 0:
                break
            length, j = _ber(buf, i + 16)
            if not length:
                start = i + 16
                continue
            items = _local_set(buf, j, length)
            out = {}
            for tag, name in PICTURE_TAGS.items():
                v = items.get(tag)
                if v and len(v) <= 8:
                    out[name] = int.from_bytes(v, 'big')
            if 'mxf_black_ref' in out and 'mxf_white_ref' in out:
                return out
            start = i + 16
    return {}
