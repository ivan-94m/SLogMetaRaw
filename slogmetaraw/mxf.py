# SPDX-License-Identifier: GPL-3.0-or-later
"""Sony XAVC MXF support: acquisition metadata in ST 436 ANC packets + NRT XML.

The header partition pack (SMPTE ST 377-1) says where header metadata, index
and essence are. Content packages are walked KLV by KLV, skipping picture and
sound with a seek; files without that layout fall back to byte-window scans.
"""
import bisect
import re
import struct

UL = b'\x06\x0e\x2b\x34'
ANC_KEY = bytes.fromhex('060e2b34010201010d01030117')  # ST 436 ANC data element
PARTITION_KEY = bytes.fromhex('060e2b34020501010d01020101')  # + 02 header / 03 body / 04 footer
INDEX_KEY = bytes.fromhex('060e2b34025301010d01020101100100')
SYSTEM_KEY = bytes.fromhex('060e2b34020501010d010301')  # + 04 / 14: system item, first in a package
ESSENCE_KEY = bytes.fromhex('060e2b34010201010d010301')  # + 05/15 picture, 06/16 sound, 07/17 data
FILL_TAIL = bytes.fromhex('0301021001000000')
SONY_DID, SONY_SDID = 0x43, 0x05
WINDOW = 4 * 1024 * 1024
CHUNK = 256 * 1024
KLV_READ = 64 * 1024
PACKAGE_HEAD = 4 * 1024         # system item, its metadata pack and the picture key
AFTER_PICTURE = 128 * 1024      # 8 sound elements (~48 KB) and the ANC (up to ~20 KB)
HEAD_MAX = 16 * 1024 * 1024     # header metadata + index kept in memory up to this size
MAX_KLVS = 64                   # per content package or essence prelude


def is_mxf(head):
    return head[:4] == UL


def _ber(buf, i):
    """(length, offset after the length) of a BER-encoded length at buf[i]."""
    if i >= len(buf):
        return None, i + 1
    b = buf[i]
    if b & 0x80:
        n = b & 0x7F
        if n == 0 or i + 1 + n > len(buf):
            return None, i + 1
        return int.from_bytes(buf[i + 1:i + 1 + n], 'big'), i + 1 + n
    return b, i + 1


def _is_fill(key):
    return key[:4] == UL and key[4:7] == b'\x01\x01\x01' and key[8:16] == FILL_TAIL


def _is_partition(key):
    return key[:13] == PARTITION_KEY and key[13] in (2, 3, 4)


def _is_system(key):
    return key[:12] == SYSTEM_KEY and key[12] in (0x04, 0x14)


def _is_essence(key):
    return key[:12] == ESSENCE_KEY


def _anc_value(v):
    """Reassemble Sony acquisition metadata from an ANC element value (ST 436 packets)."""
    if len(v) < 2:
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


class _Cursor:
    """KLV reads through a local buffer; values too large for it are skipped with a seek."""

    def __init__(self, f, chunk=KLV_READ):
        self.f = f
        self.chunk = chunk
        self.base = 0
        self.buf = b''

    def read(self, pos, n):
        rel = pos - self.base
        if rel < 0 or rel + n > len(self.buf):
            self.base, self.buf, rel = pos, self.f.read_at(pos, max(n, self.chunk)), 0
        return self.buf[rel:rel + n]

    def klv(self, pos):
        """(key, value position, value length) of the KLV at pos, or None."""
        h = self.read(pos, 25)
        if len(h) < 17 or h[:4] != UL:
            return None
        length, j = _ber(h, 16)
        if length is None:
            return None
        return h[:16], pos + j, length


def layout(f):
    """{'header_end', 'essence', 'footer'} from the header partition pack, or None.

    Header metadata starts after the pack and its KAG fill (the fill is not part
    of HeaderByteCount); the index follows it and the essence follows the index.
    """
    c = _Cursor(f)
    k = c.klv(0)
    if not k or not _is_partition(k[0]) or k[0][13] != 2:
        return None
    _key, vpos, length = k
    pack = c.read(vpos, min(length, 64))
    if len(pack) < 64:
        return None
    footer, hbc, ibc = struct.unpack('>QQQ', pack[24:48])
    pos = vpos + length
    for _ in range(8):
        k = c.klv(pos)
        if not k or not _is_fill(k[0]):
            break
        pos = k[1] + k[2]
    essence = pos + hbc + ibc
    if essence >= f.size:
        return None
    return {'header_end': pos + hbc, 'essence': essence, 'footer': footer}


def content_start(f, lay):
    """Offset of the first content package: fill, index or a body partition may come first."""
    c = _Cursor(f)
    pos = lay['essence']
    for _ in range(MAX_KLVS):
        k = c.klv(pos)
        if not k:
            return None
        key, vpos, length = k
        if _is_system(key) or _is_essence(key):
            return pos
        if _is_partition(key):
            pack = c.read(vpos, min(length, 64))
            if len(pack) < 48:
                return None
            hbc, ibc = struct.unpack('>QQ', pack[32:48])
            pos = vpos + length
            k = c.klv(pos)
            while k and _is_fill(k[0]):   # KAG fill: not counted in the byte counts
                pos = k[1] + k[2]
                k = c.klv(pos)
            pos += hbc + ibc
            continue
        pos = vpos + length
    return None


def read_package(f, pos, want_sps=False):
    """(ANC payload, (codec, SPS NAL)) of the content package at pos.

    The payload is None when pos does not start a package or the package has no
    Sony ANC; the SPS comes from the start of the picture element only.
    """
    c = _Cursor(f, KLV_READ if want_sps else PACKAGE_HEAD)
    sps = (None, None)
    first = None
    for _ in range(MAX_KLVS):
        k = c.klv(pos)
        if not k:
            break
        key, vpos, length = k
        if first is None:
            if not (_is_system(key) or _is_essence(key)):
                break
            first = key
        elif _is_system(key) or key == first or _is_partition(key):
            break  # the next content package
        if key[:13] == ANC_KEY:
            payload = _anc_value(c.read(vpos, min(length, KLV_READ)))
            if payload:
                return payload, sps
        elif _is_essence(key) and key[12] in (0x05, 0x15):
            if want_sps:
                sps = _sps_in(c.read(vpos, min(length, KLV_READ)))
            c.chunk = AFTER_PICTURE
        pos = vpos + length
    return None, sps


class Index:
    """Edit unit -> offset from the essence start, from the header partition index table."""

    def __init__(self, edit_unit_bytes=0, segments=()):
        self.edit_unit_bytes = edit_unit_bytes
        self.firsts = []
        self.segments = []   # (first edit unit, entry count, entry size, entry array)
        for seg in sorted(segments, key=lambda seg: seg[0]):
            if seg[0] < self.count:
                continue     # repeated segment
            if seg[0] > self.count:
                break        # a gap: only the contiguous part from edit unit 0 is usable
            self.firsts.append(seg[0])
            self.segments.append(seg)

    @property
    def count(self):
        return self.segments[-1][0] + self.segments[-1][1] if self.segments else 0

    def offset(self, unit):
        if self.edit_unit_bytes:
            return unit * self.edit_unit_bytes
        i = bisect.bisect_right(self.firsts, unit) - 1
        if i < 0 or unit >= self.count:
            return None
        first, _n, size, arr = self.segments[i]
        entry = arr[8 + (unit - first) * size:8 + (unit - first + 1) * size]
        # entry: temporal offset, key-frame offset, flags, then the 8-byte stream offset
        return struct.unpack('>Q', entry[3:11])[0] if len(entry) >= 11 else None


def read_index(f, lay):
    """Index table segments between the header metadata and the essence."""
    start, end = lay['header_end'], lay['essence']
    if not 0 < end - start <= HEAD_MAX:
        return Index()
    buf = f.read_at(start, end - start)
    eubc, segments = 0, []
    pos = 0
    while pos + 17 <= len(buf):
        key = buf[pos:pos + 16]
        length, v = _ber(buf, pos + 16)
        if key[:4] != UL or length is None:
            break
        if key == INDEX_KEY:
            tags = _local_set(buf, v, length)
            eubc = eubc or int.from_bytes(tags.get(0x3F05, b''), 'big')
            arr = tags.get(0x3F0A)
            if arr and len(arr) >= 8:
                n, size = struct.unpack('>II', arr[:8])
                if size >= 11 and len(arr) >= 8 + n * size:
                    segments.append((int.from_bytes(tags.get(0x3F0C, b''), 'big'), n, size, arr))
        pos = v + length
    return Index(eubc, segments)


def find_rtmd(f, pos, window=WINDOW):
    """Find the first Sony ANC metadata payload at or after file offset pos by byte scan.

    Used where no content package boundary is known (no partition pack or index).
    """
    buf = b''
    base = pos
    start = 0
    while len(buf) < window and base + len(buf) < f.size:
        chunk = f.read_at(base + len(buf), CHUNK)
        if not chunk:
            break   # the file got shorter than when it was opened
        buf += chunk
        while True:
            i = buf.find(ANC_KEY, start)
            if i < 0:
                start = max(0, len(buf) - 16)
                break
            if i + 32 > len(buf):
                break
            length, vs = _ber(buf, i + 16)
            if length is None:
                start = i + 16
                continue
            if vs + length > len(buf):
                break  # need more data
            payload = _anc_value(buf[vs:vs + length])
            if payload:
                return payload
            start = i + 16
    return None


SPS_RE = re.compile(rb'\x00\x00\x01(?:([\x07\x27\x47\x67])|(\x42\x01))')


def _sps_in(buf, pos=0):
    m = SPS_RE.search(buf, pos)
    if m:
        j = buf.find(b'\x00\x00\x01', m.start() + 4)
        if j > 0:
            return ('avc' if m.group(1) else 'hevc'), buf[m.start() + 3:j]
    return None, None


def find_sps(f, window=8 * 1024 * 1024, start=0):
    """Return (codec, SPS NAL bytes) searching by start code from start.

    From offset 0 this can match inside header metadata or index; callers that
    know where the essence starts pass it.
    """
    buf = b''
    while len(buf) < window and start + len(buf) < f.size:
        chunk = f.read_at(start + len(buf), CHUNK)
        if not chunk:
            break
        seen = len(buf)
        buf += chunk
        found = _sps_in(buf, max(0, seen - 4096))   # an SPS is far shorter than 4 KB
        if found[1]:
            return found
    return None, None


def find_nrt_xml(f, head=WINDOW):
    """Embedded NonRealTimeMeta XML: in the header metadata, else in the tail of the file."""
    for pos, n in ((0, head), (max(0, f.size - WINDOW), WINDOW)):
        buf = f.read_at(pos, min(n, f.size - pos))
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

    Reads only the head of the file, where the header metadata lives. Returns an
    empty dict when no picture descriptor is found or it states no reference levels.
    """
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
