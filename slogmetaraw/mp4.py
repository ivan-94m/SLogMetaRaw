# SPDX-License-Identifier: GPL-3.0-or-later
"""Minimal ISO-BMFF (MP4/MOV) reader.

Reads only box headers and the few boxes we need (moov, top-level meta,
sample tables) via seek, so even multi-GB clips cost a few KB of I/O.
"""
import struct

CONTAINERS = {b'moov', b'trak', b'mdia', b'minf', b'stbl', b'dinf', b'edts', b'udta'}


class CountingFile:
    """File wrapper that counts bytes actually read (used for perf checks)."""

    def __init__(self, path):
        self._f = open(path, 'rb')
        self.bytes_read = 0
        self._f.seek(0, 2)
        self.size = self._f.tell()
        self._f.seek(0)

    def read_at(self, pos, n):
        self._f.seek(pos)
        data = self._f.read(n)
        self.bytes_read += len(data)
        return data

    def close(self):
        self._f.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def iter_boxes(f, start, end):
    """Yield (type, box_start, header_len, box_size) for boxes in [start, end)."""
    pos = start
    while pos + 8 <= end:
        hdr = f.read_at(pos, 16)
        if len(hdr) < 8:
            return
        size, typ = struct.unpack('>I4s', hdr[:8])
        hlen = 8
        if size == 1:
            size = struct.unpack('>Q', hdr[8:16])[0]
            hlen = 16
        elif size == 0:
            size = end - pos
        if size < hlen:
            return
        yield typ, pos, hlen, size
        pos += size


def find_child(f, start, end, typ):
    for t, p, hl, s in iter_boxes(f, start, end):
        if t == typ:
            return p, hl, s
    return None


def box_payload(f, box):
    p, hl, s = box
    return f.read_at(p + hl, s - hl)


class Track:
    def __init__(self):
        self.handler = None
        self.codec = None          # sample entry fourcc
        self.sample_entry = b''    # full first sample entry bytes
        self.timescale = None
        self.duration = None
        self.tables = {}           # b'stsz' -> payload bytes, etc.

    # -- sample table helpers -------------------------------------------
    def sample_count(self):
        stsz = self.tables.get(b'stsz')
        if not stsz:
            return 0
        return struct.unpack('>I', stsz[8:12])[0]

    def sample_size(self, idx):
        stsz = self.tables[b'stsz']
        fixed, count = struct.unpack('>II', stsz[4:12])
        if fixed:
            return fixed
        return struct.unpack('>I', stsz[12 + 4 * idx:16 + 4 * idx])[0]

    def chunk_offsets(self):
        if b'stco' in self.tables:
            d = self.tables[b'stco']
            n = struct.unpack('>I', d[4:8])[0]
            return list(struct.unpack('>%dI' % n, d[8:8 + 4 * n]))
        d = self.tables[b'co64']
        n = struct.unpack('>I', d[4:8])[0]
        return list(struct.unpack('>%dQ' % n, d[8:8 + 8 * n]))

    def sample_offsets(self, wanted):
        """Return {sample_index: file_offset} for the requested sample indices."""
        wanted = sorted(set(i for i in wanted if 0 <= i < self.sample_count()))
        if not wanted:
            return {}
        stsc = self.tables[b'stsc']
        n = struct.unpack('>I', stsc[4:8])[0]
        runs = [struct.unpack('>III', stsc[8 + 12 * i:20 + 12 * i]) for i in range(n)]
        chunks = self.chunk_offsets()
        out = {}
        stsz = self.tables[b'stsz']
        fixed = struct.unpack('>I', stsz[4:8])[0]
        sample = 0
        w = 0
        for ri, (first_chunk, per_chunk, _desc) in enumerate(runs):
            last_chunk = runs[ri + 1][0] - 1 if ri + 1 < len(runs) else len(chunks)
            for c in range(first_chunk, last_chunk + 1):
                if w >= len(wanted):
                    return out
                chunk_end = sample + per_chunk
                if wanted[w] >= chunk_end:
                    sample = chunk_end
                    continue
                off = chunks[c - 1]
                for s in range(sample, chunk_end):
                    if w < len(wanted) and s == wanted[w]:
                        out[s] = off
                        w += 1
                    off += fixed if fixed else self.sample_size(s)
                sample = chunk_end
        return out


def _parse_trak(f, trak):
    tr = Track()
    p, hl, s = trak

    def walk(a, b):
        for t, bp, bhl, bs in iter_boxes(f, a, b):
            if t in (b'mdia', b'minf'):
                walk(bp + bhl, bp + bs)
            elif t == b'mdhd':
                d = f.read_at(bp + bhl, bs - bhl)
                if d[0] == 1:
                    tr.timescale, tr.duration = struct.unpack('>IQ', d[20:32])
                else:
                    tr.timescale, tr.duration = struct.unpack('>II', d[12:20])
            elif t == b'hdlr':
                tr.handler = f.read_at(bp + bhl + 8, 4)
            elif t == b'stbl':
                for t2, p2, hl2, s2 in iter_boxes(f, bp + bhl, bp + bs):
                    if t2 in (b'stsd', b'stsz', b'stco', b'co64', b'stsc', b'stts'):
                        tr.tables[t2] = f.read_at(p2 + hl2, s2 - hl2)
                stsd = tr.tables.get(b'stsd')
                if stsd and len(stsd) >= 16:
                    esize = struct.unpack('>I', stsd[8:12])[0]
                    tr.codec = stsd[12:16]
                    tr.sample_entry = stsd[8:8 + esize]

    walk(p + hl, p + s)
    return tr


class MP4:
    def __init__(self, f):
        self.f = f
        self.tracks = []
        self.meta_xml = None          # NonRealTimeMeta XML (bytes)
        self.meta_items = {}          # item name -> bytes (e.g. 'Look Control data')
        self.brand = None
        self._parse()

    def _parse(self):
        f = self.f
        for t, p, hl, s in iter_boxes(f, 0, f.size):
            if t == b'ftyp':
                self.brand = f.read_at(p + hl, 4).decode('latin1')
            elif t == b'moov':
                for t2, p2, hl2, s2 in iter_boxes(f, p + hl, p + s):
                    if t2 == b'trak':
                        self.tracks.append(_parse_trak(f, (p2, hl2, s2)))
            elif t == b'meta':
                self._parse_meta(p + hl + 4, p + s)

    def _parse_meta(self, a, b):
        """Top-level 'meta' (handler 'nrtm'): xml box + items in idat."""
        f = self.f
        names = {}
        locs = {}
        idat_start = None
        for t, p, hl, s in iter_boxes(f, a, b):
            if t == b'xml ':
                self.meta_xml = f.read_at(p + hl + 4, s - hl - 4)
            elif t == b'iinf':
                d = f.read_at(p + hl, s - hl)
                ver = d[0]
                q = 6 if ver == 0 else 8
                while q + 8 <= len(d):
                    size = struct.unpack('>I', d[q:q + 4])[0]
                    if size < 8:
                        break
                    e = d[q + 8:q + size]
                    ev = d[q + 8]
                    if ev >= 2:
                        item_id = struct.unpack('>H', e[4:6])[0]
                        name = e[12:].split(b'\0')[0]
                    else:
                        item_id = struct.unpack('>H', e[4:6])[0]
                        name = e[8:].split(b'\0')[0]
                    names[item_id] = name.decode('utf-8', 'replace')
                    q += size
            elif t == b'iloc':
                d = f.read_at(p + hl, s - hl)
                ver = d[0]
                sz = d[4]
                off_size, len_size = sz >> 4, sz & 15
                base_size = d[5] >> 4
                idx_size = d[5] & 15 if ver in (1, 2) else 0
                q = 6
                count = struct.unpack('>H', d[q:q + 2])[0]
                q += 2

                def rd(n):
                    nonlocal q
                    v = int.from_bytes(d[q:q + n], 'big') if n else 0
                    q += n
                    return v

                for _ in range(count):
                    item_id = rd(2)
                    method = 0
                    if ver in (1, 2):
                        method = rd(2) & 15
                    rd(2)  # data_reference_index
                    base = rd(base_size)
                    ext = rd(2)
                    for _e in range(ext):
                        if idx_size:
                            rd(idx_size)
                        eo = rd(off_size)
                        el = rd(len_size)
                        locs.setdefault(item_id, (method, base + eo, el))
            elif t == b'idat':
                idat_start = p + hl
        for item_id, (method, off, length) in locs.items():
            name = names.get(item_id, 'item%d' % item_id)
            if method == 1 and idat_start is not None:
                self.meta_items[name] = f.read_at(idat_start + off, length)
            elif method == 0:
                self.meta_items[name] = f.read_at(off, length)

    def track(self, handler=None, codec=None):
        for t in self.tracks:
            if (handler is None or t.handler == handler) and (codec is None or t.codec == codec):
                return t
        return None
