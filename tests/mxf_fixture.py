# SPDX-License-Identifier: GPL-3.0-or-later
"""Build a small but structurally valid Sony XAVC MXF, for the scan tests.

The clip that exposed the bug is 97 minutes of 4K on an external drive: far too
big to keep as a fixture, and we never had a copy of it. What matters about it is
its SHAPE, and that is reproducible in a few hundred kilobytes: an ST 377-1 header
partition pack whose HeaderByteCount and IndexByteCount push the first essence KLV
past the scanner's window, then the essence, then a Random Index Pack in the tail.

Everything here is written the way Sony writes it, so a test that passes against
this fixture is testing the real parser and not a mock.
"""
import struct

UL_PREFIX = b'\x06\x0e\x2b\x34'
HEADER_PARTITION_KEY = bytes.fromhex('060e2b34020501010d01020101020400')
BODY_PARTITION_KEY = bytes.fromhex('060e2b34020501010d01020101030400')
FOOTER_PARTITION_KEY = bytes.fromhex('060e2b34020501010d01020101040400')
RIP_KEY = bytes.fromhex('060e2b34020501010d01020101110100')
ANC_KEY = bytes.fromhex('060e2b34010201010d01030117010200')   # ST 436 ANC data element
FILLER_KEY = bytes.fromhex('060e2b34010101020301021001000000')
CAMERA_SET = bytes.fromhex('060e2b340253010c') + bytes.fromhex('0c02010102010000')
LENS_SET = bytes.fromhex('060e2b340253010c') + bytes.fromhex('0c02010101010000')

PARTITION_FIELDS = '>HHIQQQQQIQI'   # major minor KAG this prev footer hdrBytes idxBytes idxSID bodyOff bodySID


def ber(n):
    """Long-form BER length, the way MXF writes it (4-byte form)."""
    return bytes([0x83]) + n.to_bytes(3, 'big')


def klv(key, value):
    return key + ber(len(value)) + value


def partition_pack(key, this=0, prev=0, footer=0, header_bytes=0, index_bytes=0,
                   index_sid=0, body_offset=0, body_sid=0, kag=512):
    v = struct.pack(PARTITION_FIELDS, 1, 3, kag, this, prev, footer,
                    header_bytes, index_bytes, index_sid, body_offset, body_sid)
    v += bytes(16)                                  # OperationalPattern UL
    v += struct.pack('>II', 1, 16) + bytes(16)      # EssenceContainers batch
    return klv(key, v)


def local_set(key, tags):
    """An MXF local set: 2-byte tag, 2-byte length, value."""
    body = b''.join(struct.pack('>HH', t, len(v)) + v for t, v in tags)
    return klv(key, body)


def ul_value(tail):
    """A 16-byte UL whose last four bytes carry the enumeration (rtmd._ul_tail)."""
    return bytes.fromhex('060e2b3404010105') + bytes(4) + struct.pack('>I', tail)


def sony_primaries_ul(tail):
    """rtmd._primaries only reads the Sony table when bytes 8..12 say so."""
    return bytes.fromhex('060e2b3404010105') + b'\x0e\x06\x04\x01' + struct.pack('>I', tail)


def acquisition_payload(white_balance_k=5600, tint_hundredths=1517, exposure_index=800,
                        iso=12800, gamma_tail=0x01010605, primaries_tail=0x01030105,
                        lens='FE 24-105mm F4 G OSS', iris_raw=49152):
    """The bytes a Sony ANC packet carries: KLV packs of local tags.

    iris_raw is the encoding rtmd._fstop reads: 2 ** (8 * (1 - raw / 65536)),
    so 49152 is f/4.0.
    """
    camera = local_set(CAMERA_SET, [
        (0x810b, struct.pack('>H', iso)),
        (0x810e, struct.pack('>H', white_balance_k)),
        (0x8115, struct.pack('>H', exposure_index)),
        (0x811f, struct.pack('>h', tint_hundredths)),
        (0x3210, ul_value(gamma_tail)),
        (0x3219, sony_primaries_ul(primaries_tail)),
    ])
    lens_set = local_set(LENS_SET, [
        (0x8000, struct.pack('>H', iris_raw)),
        (0x8007, lens.encode('utf-8')),
    ])
    return camera + lens_set


# An ANC packet's data count is a single byte, so Sony splits the acquisition
# metadata across however many packets it takes and the reader concatenates them.
UDW_MAX = 254


def anc_packet(chunk, seq, did=0x43, sdid=0x05):
    arr = bytes([did, sdid, len(chunk) + 1, seq]) + chunk        # DID, SDID, DC, seq, UDW
    pkt = struct.pack('>HBBH', 9, 0x01, 0x04, 1)                 # line, wrapping, coding, samples
    return pkt + struct.pack('>II', len(arr), 1) + arr           # element count, element size


def anc_element(payload, did=0x43, sdid=0x05, extra=()):
    """One ST 436 ANC data element carrying `payload`, split across packets."""
    chunks = [payload[i:i + UDW_MAX - 1] for i in range(0, len(payload), UDW_MAX - 1)] or [b'']
    pkts = list(extra) + [anc_packet(c, i, did, sdid) for i, c in enumerate(chunks)]
    return klv(ANC_KEY, struct.pack('>H', len(pkts)) + b''.join(pkts))


def rip(partitions):
    """Random Index Pack: (BodySID, ByteOffset) pairs, then its own total length."""
    v = b''.join(struct.pack('>IQ', sid, off) for sid, off in partitions)
    total = 16 + 4 + len(v) + 4     # key + BER(4) + pairs + this length field
    return RIP_KEY + ber(len(v) + 4) + v + struct.pack('>I', total)


def build(path, essence_gap=6 * 1024 * 1024, payload=None, before_sony=None,
          body_partitions=1, tail_pad=0, with_rip=True):
    """Write a fixture MXF and return {'path', 'essence', 'anc', 'size'}.

    essence_gap    bytes of HeaderByteCount + IndexByteCount, i.e. how far the first
                   essence KLV sits from the top of the file. 6 MB reproduces the
                   reported clip, where a per-frame index for 145800 frames pushes
                   the essence past the old 4 MiB scan window.
    before_sony    an extra ANC element (a timecode one, say) written ahead of the
                   Sony element, to check the scanner does not stop at the first
                   ANC key it sees.
    """
    payload = acquisition_payload() if payload is None else payload
    header_bytes, index_bytes = 128 * 1024, essence_gap - 128 * 1024
    parts, offsets = [], []
    pack = partition_pack(HEADER_PARTITION_KEY, header_bytes=header_bytes,
                          index_bytes=index_bytes, index_sid=1, body_sid=0)
    parts.append(pack)
    offsets.append((0, 0))
    parts.append(bytes(header_bytes + index_bytes))      # header metadata + index table
    essence_at = len(pack) + header_bytes + index_bytes

    anc_at = None
    for b in range(body_partitions):
        if b:
            offsets.append((2, sum(len(p) for p in parts)))
            parts.append(partition_pack(BODY_PARTITION_KEY,
                                        this=sum(len(p) for p in parts), body_sid=2))
        if before_sony:
            parts.append(before_sony)
        picture = klv(FILLER_KEY, bytes(3 * 1024 * 1024))   # a 4K long-GOP anchor frame
        parts.append(picture)
        if anc_at is None:
            anc_at = sum(len(p) for p in parts)
        parts.append(anc_element(payload))

    footer_at = sum(len(p) for p in parts)
    parts.append(partition_pack(FOOTER_PARTITION_KEY, this=footer_at, footer=footer_at))
    offsets.append((0, footer_at))
    if tail_pad:
        parts.append(bytes(tail_pad))
    if with_rip:
        parts.append(rip(offsets))      # a file still being written has none
    data = b''.join(parts)
    with open(path, 'wb') as fh:
        fh.write(data)
    return {'path': path, 'essence': essence_at, 'anc': anc_at, 'size': len(data),
            'footer': footer_at}
