# SPDX-License-Identifier: GPL-3.0-or-later
"""Render the reference chart of the three false colours of the SLogMetaRaw node.

Usage: python3 tools/make_falsecolor_chart.py [output png]
       (default: docs/falsecolor_bands.png)

Each strip is produced by the same code the node runs (tests/develop_model.py, the
reference for ofx/SLogMetaRaw/math/FalseColor.h), on a neutral surface pushed off by a
known amount, so the chart cannot drift away from what the plugin actually does:

  exposure     a ramp from -8 to +6 stops around 18% grey
  temperature  a neutral surface whose light is 1200 K warm .. 1200 K cool of the slider
  tint         the same, 35 tint units green .. 35 magenta
"""
import os
import struct
import sys
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import develop_model as dm  # noqa: E402

SG3C, SLOG3 = 8, 9
WIDTH, STRIP, GAP = 900, 150, 10
K0, TINT0 = 5600.0, 0.0
FRAME = (0.08, 0.08, 0.09)


def neutral(shot_k, shot_tint, stops=0.0):
    """XYZ of a neutral surface shot under that light, seen with the slider at K0/TINT0."""
    code = dm.encode1(0.18 * (2 ** stops), SLOG3)
    out = dm.develop([code] * 3, SG3C, SLOG3, shot=(shot_k, shot_tint, 800), temp=K0, tint=TINT0)
    return dm.mul(dm.MATS[SG3C][0], [dm.decode1(c, SLOG3) for c in out])


def strip(mode, calibration):
    rows = []
    for y in range(STRIP):
        row = bytearray([0])
        for x in range(WIDTH):
            f = x / (WIDTH - 1)
            if mode == 1:
                xyz = neutral(K0, TINT0, stops=-8.0 + 14.0 * f)
            elif mode == 2:
                xyz = neutral(K0 + (-1200.0 + 2400.0 * f), TINT0)
            else:
                xyz = neutral(K0, TINT0 + (-35.0 + 70.0 * f))
            colour = FRAME if (y < 6 or y >= STRIP - 6) else dm.false_color(xyz, mode, *calibration)
            for channel in colour:
                row.append(int(max(0.0, min(1.0, channel)) * 255 + 0.5))
        rows.append(bytes(row))
    return rows


def write_png(path, rows, width):
    def chunk(tag, data):
        body = tag + data
        return struct.pack('>I', len(data)) + body + struct.pack('>I', zlib.crc32(body) & 0xffffffff)
    raw = b''.join(rows)
    out = b'\x89PNG\r\n\x1a\n'
    out += chunk(b'IHDR', struct.pack('>IIBBBBB', width, len(rows), 8, 2, 0, 0, 0))
    out += chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b'')
    with open(path, 'wb') as fh:
        fh.write(out)


def main(argv):
    path = argv[1] if len(argv) > 1 else os.path.join(ROOT, 'docs', 'falsecolor_bands.png')
    calibration = dm.fc_calibration(K0, TINT0)
    rows = []
    for i, mode in enumerate((1, 2, 3)):
        if i:
            rows += [bytes([0]) + bytes([20, 20, 22]) * WIDTH] * GAP
        rows += strip(mode, calibration)
    write_png(path, rows, WIDTH)
    print('written %s (%dx%d)' % (path, WIDTH, len(rows)))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
