# SPDX-License-Identifier: GPL-3.0-or-later
"""Draw the three false-colour toggle icons of the SLogMetaRaw OpenFX node.

Usage: python3 tools/make_param_icons.py [output dir]   (default: ofx/SLogMetaRaw)

Each icon is a disc split down the middle into the two ends of the axis its
control moves, which is the same idea as the half-black/half-white disc every
editor reads as "contrast":

    fc_exposure.png     black | white        stops around 18% grey
    fc_temperature.png  blue  | orange       cool | warm, along the Planckian locus
    fc_tint.png         green | magenta      the axis across it

Written with zlib only, so the build needs nothing installed.
"""
import os
import struct
import sys
import zlib

SIZE = 256
SS = 4                      # supersampling factor for the edges
RING = (0.62, 0.64, 0.68)   # a thin neutral rim, so the disc reads on any panel

ICONS = {
    'fc_exposure':    ((0.07, 0.07, 0.08), (0.94, 0.94, 0.94)),
    'fc_temperature': ((0.17, 0.55, 1.00), (1.00, 0.54, 0.12)),
    'fc_tint':        ((0.24, 0.81, 0.29), (0.88, 0.29, 0.82)),
}


def disc(left, right):
    """RGBA rows of one icon, anti-aliased by supersampling."""
    n = SIZE * SS
    c = (n - 1) / 2.0
    outer = n * 0.47
    inner = outer - n * 0.045
    rows = []
    for y in range(SIZE):
        row = bytearray([0])
        for x in range(SIZE):
            acc = [0.0, 0.0, 0.0, 0.0]
            for sy in range(SS):
                for sx in range(SS):
                    px, py = x * SS + sx - c, y * SS + sy - c
                    r = (px * px + py * py) ** 0.5
                    if r > outer:
                        continue
                    col = RING if r > inner else (left if px < 0 else right)
                    acc[0] += col[0]
                    acc[1] += col[1]
                    acc[2] += col[2]
                    acc[3] += 1.0
            k = SS * SS
            a = acc[3] / k
            if a > 0:                      # un-premultiply, PNG alpha is straight
                for i in range(3):           # the colours above are already display values
                    row.append(int(min(1.0, acc[i] / acc[3]) * 255 + 0.5))
            else:
                row += b'\x00\x00\x00'
            row.append(int(a * 255 + 0.5))
        rows.append(bytes(row))
    return b''.join(rows)


def write_png(path, raw, width, height):
    def chunk(tag, data):
        body = tag + data
        return struct.pack('>I', len(data)) + body + struct.pack('>I', zlib.crc32(body) & 0xffffffff)
    out = b'\x89PNG\r\n\x1a\n'
    out += chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
    out += chunk(b'IDAT', zlib.compress(raw, 9))
    out += chunk(b'IEND', b'')
    with open(path, 'wb') as fh:
        fh.write(out)


def main(argv):
    out_dir = argv[1] if len(argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'ofx', 'SLogMetaRaw')
    for name, (left, right) in ICONS.items():
        path = os.path.join(out_dir, name + '.png')
        write_png(path, disc(left, right), SIZE, SIZE)
        print('written', path)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
