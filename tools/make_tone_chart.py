# SPDX-License-Identifier: GPL-3.0-or-later
"""Render the reference chart of the tone stage of the SLogMetaRaw node.

Usage: python3 tools/make_tone_chart.py [output png]
       (default: docs/tone_curve.png)

Eight strips. The first six ride the same scene ramp from -8 to +8 stops around
18% grey; the last two ride a saturated blue ramp, which is where the stage this
replaces failed:

  1  no press, straight to Rec.709         - clips at +2.47 stops
  2  the operator two versions ago         - a shelf: it offsets the top, never rolls it
  3  the press at full strength            - folds the container inside the same white
  4  Kodak 2383 print emulation            - the measured reference
  5  bright skin, 0 to +5 stops            - must not go flat pink
  6  blue sky, 0 to +6 stops               - must not stay neon
  7  blue ramp through the OLD stage       - goes DARK past the knee: the inversion
  8  blue ramp through this one            - monotone all the way up

Strips 1-3 and 5-8 use the same code the node runs (tests/develop_model.py, the
reference for ofx/SLogMetaRaw/DevelopMath.h), so the chart cannot drift from the
plugin. Strip 4 is sampled from the LUT Resolve ships, if it is installed.
"""
import math
import os
import struct
import sys
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import develop_model as dm  # noqa: E402

SG3C = 8
WIDTH, STRIP, GAP = 960, 96, 8
EV_LO, EV_HI = -8.0, 8.0
SKIN, SKY = (0.29, 0.20, 0.155), (0.06, 0.12, 0.30)
E_TOP = dm.tank_top(9)        # the container an S-Log3 clip records, +7.74 stops
LUT_PATH = ('/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT/'
            'Film Looks/Rec709 Kodak 2383 D65.cube')


def display(lin):
    """Display code from a display-linear value, for the PNG."""
    return max(0.0, min(1.0, lin)) ** (1 / 2.2)


def old_operator(ev, highlights=-1.0):
    """The shelf this replaces: a gain whose weight saturates at +-5 stops."""
    wh = min(max(ev / 5.0, 0.0), 1.0)
    return 0.18 * 2 ** (ev + highlights * 2 * wh * wh)


def old_stage(rgb, highlights=-1.0):
    """The ratio-plus-purity pair this replaces. Kept so the chart can show the
    defect rather than assert it: once f(norm) reaches its asymptote it is flat while
    purity = t^k(t) keeps falling, so the product falls and a brighter chromatic pixel
    comes out darker."""
    norm = dm.tone_norm(rgb)
    if norm <= 1e-6:
        return list(rgb)
    t = (norm ** -3.0 + (-highlights) ** 3.0) ** (-1 / 3.0) / norm
    out = [c * t for c in rgb]
    k = 0.5 * (1.0 + max(1.0 - t, 0.0))
    purity = t ** k if t < 1 else 1.0
    if purity < 1.0:
        yl = dm.mul(dm.MATS[SG3C][0], out)[1]
        out = [yl + (c - yl) * purity for c in out]
    return out


def load_lut(path):
    size, data = None, []
    for line in open(path, encoding='utf-8', errors='replace'):
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        if s.startswith('LUT_3D_SIZE'):
            size = int(s.split()[-1])
            continue
        if s[0].isalpha() or s[0] == '"':
            continue
        p = s.split()
        if len(p) == 3:
            try:
                data.append(tuple(float(v) for v in p))
            except ValueError:
                pass
    return size, data


def lut_neutral(size, data, x):
    """The LUT's neutral axis, interpolated - sampling the nearest grid point would
    print the 33-point lattice as steps and misrepresent the reference."""
    g = min(max(x, 0.0), 1.0) * (size - 1)
    i0 = min(int(g), size - 1)
    i1 = min(i0 + 1, size - 1)
    f = g - i0
    a = data[i0 + i0 * size + i0 * size * size][1]
    b = data[i1 + i1 * size + i1 * size * size][1]
    return a + (b - a) * f


def cineon(lin):
    off = 10 ** ((95.0 - 685.0) * 0.002 / 0.6)
    return (685.0 + math.log10(max(lin * (1 - off) + off, 1e-10)) * 0.6 / 0.002) / 1023.0


def strips(lut):
    rows = []
    for mode in range(8):
        for y in range(STRIP):
            row = bytearray([0])
            for x in range(WIDTH):
                f = x / (WIDTH - 1)
                if y < 3 or y >= STRIP - 3:
                    row += bytes([20, 20, 22])
                    continue
                if mode < 4:
                    ev = EV_LO + (EV_HI - EV_LO) * f
                    lin = 0.18 * 2 ** ev
                    if mode == 0:
                        c = [display(lin)] * 3
                    elif mode == 1:
                        c = [display(old_operator(ev))] * 3
                    elif mode == 2:
                        c = [display(v) for v in dm.tone([lin] * 3, SG3C, -1.0, 0.0, 0.0, E_TOP)]
                    else:
                        c = ([lut_neutral(lut[0], lut[1], cineon(lin))] * 3 if lut
                             else [0.12, 0.12, 0.14])
                elif mode < 6:
                    base, top = (SKIN, 5.0) if mode == 4 else (SKY, 6.0)
                    rgb = [v * 2 ** (top * f) for v in base]
                    c = [display(v) for v in dm.tone(rgb, SG3C, -1.0, 0.0, 0.0, E_TOP)]
                else:
                    rgb = [v * 2 ** (8.0 * f) for v in SKY]
                    out = (old_stage(rgb) if mode == 6
                           else dm.tone(rgb, SG3C, -1.0, 0.0, 0.0, E_TOP))
                    c = [display(v) for v in out]
                for ch in c:
                    row.append(int(max(0.0, min(1.0, ch)) * 255 + 0.5))
            rows.append(bytes(row))
        if mode < 7:
            rows += [bytes([0]) + bytes([20, 20, 22]) * WIDTH] * GAP
    return rows


def write_png(path, rows, width):
    def chunk(tag, data):
        body = tag + data
        return struct.pack('>I', len(data)) + body + struct.pack('>I', zlib.crc32(body) & 0xffffffff)
    out = b'\x89PNG\r\n\x1a\n'
    out += chunk(b'IHDR', struct.pack('>IIBBBBB', width, len(rows), 8, 2, 0, 0, 0))
    out += chunk(b'IDAT', zlib.compress(b''.join(rows), 9)) + chunk(b'IEND', b'')
    with open(path, 'wb') as fh:
        fh.write(out)


def main(argv):
    path = argv[1] if len(argv) > 1 else os.path.join(ROOT, 'docs', 'tone_curve.png')
    lut = load_lut(LUT_PATH) if os.path.exists(LUT_PATH) else None
    if not lut:
        print('nota: il LUT Kodak 2383 non e installato, la quarta striscia resta vuota')
    rows = strips(lut)
    write_png(path, rows, WIDTH)
    print('written %s (%dx%d)' % (path, WIDTH, len(rows)))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
