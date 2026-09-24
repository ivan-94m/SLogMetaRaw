# SPDX-License-Identifier: GPL-3.0-or-later
"""Minimal ISO-BMFF (MP4/MOV) reader.

Reads only box headers and the few boxes we need (moov, top-level meta,
sample tables), so even multi-GB clips cost a few KB of I/O.
"""
import os
import struct

MAX_BOXES = 4096               # per level: a non-ISO file must not become a long walk
PRELOAD_MAX = 64 * 1024 * 1024
META_PRELOAD = 64 * 1024


class CountingFile:
    """Positional reads that count system calls and bytes (the performance tests use both).

    No read-ahead: a buffered file reads st_blksize (1 MiB on exFAT disks) for
    every 2 KB sample. preload() keeps one explicit window in memory instead.
    """

    def __init__(self, path):
        self._fd = os.open(path, os.O_RDONLY)
        try:
            self.size = os.fstat(self._fd).st_size
        except OSError:
            os.close(self._fd)
            raise
        self.bytes_read = 0
        self.reads = 0
        self._base = 0
        self._window = b''

    def _pread(self, pos, n):
        n = max(0, min(n, self.size - pos))
        if n == 0 or pos < 0:
            return b''
        data = os.pread(self._fd, n, pos)
        self.reads += 1
        self.bytes_read += len(data)
        return data

    def preload(self, pos, n):
        rel = pos - self._base
        if not (rel >= 0 and rel + min(n, self.size - pos) <= len(self._window)):
            self._base, self._window = pos, self._pread(pos, n)

    def read_at(self, pos, n):
        rel = pos - self._base
        if rel >= 0 and rel + n <= len(self._window):
            return self._window[rel:rel + n]
        return self._pread(pos, n)

    def close(self):
        os.close(self._fd)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def iter_boxes(f, start, end):
    """Yield (type, box_start, header_len, box_size) for boxes in [start, end)."""
    pos = start
    for _ in range(MAX_BOXES):
        if pos + 8 > end:
            return
        hdr = f.read_at(pos, 16)
        if len(hdr) < 8:
            return
        size, typ = struct.unpack('>I4s', hdr[:8])
        hlen = 8
        if size == 1:
            if len(hdr) < 16:
                return
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
        if not stsz or len(stsz) < 12:
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
            n = min(struct.unpack('>I', d[4:8])[0], (len(d) - 8) // 4)
            return list(struct.unpack('>%dI' % n, d[8:8 + 4 * n]))
        d = self.tables[b'co64']
        n = min(struct.unpack('>I', d[4:8])[0], (len(d) - 8) // 8)
        return list(struct.unpack('>%dQ' % n, d[8:8 + 8 * n]))

    def sample_offsets(self, wanted):
        """Return {sample_index: file_offset} for the requested sample indices."""
        wanted = sorted(set(i for i in wanted if 0 <= i < self.sample_count()))
        if not wanted or b'stsc' not in self.tables or not (b'stco' in self.tables or b'co64' in self.tables):
            return {}
        stsc = self.tables[b'stsc']
        n = min(struct.unpack('>I', stsc[4:8])[0], (len(stsc) - 8) // 12)
        runs = [struct.unpack('>III', stsc[8 + 12 * i:20 + 12 * i]) for i in range(n)]
        chunks = self.chunk_offsets()
        out = {}
        stsz = self.tables[b'stsz']
        fixed = struct.unpack('>I', stsz[4:8])[0]
        sample = 0
        w = 0
        for ri, (first_chunk, per_chunk, _desc) in enumerate(runs):
            last_chunk = min(runs[ri + 1][0] - 1 if ri + 1 < len(runs) else len(chunks), len(chunks))
            if per_chunk == 0 or first_chunk < 1:
                continue   # a damaged run: skipping it must not walk billions of empty chunks
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
                if len(d) >= 32 and d[0] == 1:
                    tr.timescale, tr.duration = struct.unpack('>IQ', d[20:32])
                elif len(d) >= 20:
                    tr.timescale, tr.duration = struct.unpack('>II', d[12:20])
            elif t == b'hdlr' and tr.handler is None:
                # QuickTime repeats hdlr inside minf (data handler 'alis'): the media one comes first
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
        self.items = {}               # item name -> (file offset, length), e.g. 'Look Control data'
        self.brand = None
        self._parse()

    def _parse(self):
        f = self.f
        f.preload(0, META_PRELOAD)     # ftyp, uuid and free headers in one read
        for t, p, hl, s in iter_boxes(f, 0, f.size):
            if t == b'ftyp':
                self.brand = f.read_at(p + hl, 4).decode('latin1')
            elif t == b'moov':
                if s <= PRELOAD_MAX:
                    f.preload(p, s + 16)   # + the next top-level header
                for t2, p2, hl2, s2 in iter_boxes(f, p + hl, p + s):
                    if t2 == b'trak':
                        self.tracks.append(_parse_trak(f, (p2, hl2, s2)))
            elif t == b'meta':
                f.preload(p, min(s, META_PRELOAD))
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
                while q + 14 <= len(d):
                    size = struct.unpack('>I', d[q:q + 4])[0]
                    if size < 8:
                        break
                    e = d[q + 8:q + size]
                    if len(e) < 8:
                        break
                    ev = e[0]
                    if ev >= 3:   # 32-bit item_ID
                        item_id = struct.unpack('>I', e[4:8])[0]
                        name = e[14:].split(b'\0')[0]
                    elif ev == 2:
                        item_id = struct.unpack('>H', e[4:6])[0]
                        name = e[12:].split(b'\0')[0]
                    else:
                        item_id = struct.unpack('>H', e[4:6])[0]
                        name = e[8:].split(b'\0')[0]
                    names[item_id] = name.decode('utf-8', 'replace')
                    q += size
            elif t == b'iloc':
                d = f.read_at(p + hl, s - hl)
                if len(d) < 8:
                    continue
                ver = d[0]
                sz = d[4]
                off_size, len_size = sz >> 4, sz & 15
                base_size = d[5] >> 4
                idx_size = d[5] & 15 if ver in (1, 2) else 0
                q = 6

                def rd(n):
                    nonlocal q
                    v = int.from_bytes(d[q:q + n], 'big') if n else 0
                    q += n
                    return v

                id_size = 4 if ver == 2 else 2   # ISO 14496-12: 32-bit count and item_ID in version 2
                count = rd(id_size)
                for _ in range(count):
                    if q >= len(d):
                        break
                    item_id = rd(id_size)
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
                self.items[name] = (idat_start + off, length)
            elif method == 0:
                self.items[name] = (off, length)

    def item(self, name):
        """Bytes of a meta item, read only on request (the LUT alone is ~434 KB)."""
        loc = self.items.get(name)
        return self.f.read_at(*loc) if loc else None

    def track(self, handler=None, codec=None):
        for t in self.tracks:
            if (handler is None or t.handler == handler) and (codec is None or t.codec == codec):
                return t
        return None
