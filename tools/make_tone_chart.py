# SPDX-License-Identifier: GPL-3.0-or-later
"""Render the reference chart of the tone stage of the S-Log MetaRaw node (v5).

Usage: python3 tools/make_tone_chart.py [output png]
       (default: docs/tone_curve.png)

Strips of the same scene ramp from -8 to +8 stops around 18% grey, shown through a plain
Rec.709 display (clip at +2.47 stops), then two colour ramps:

  1  no tone                              - clips at +2.47 stops
  2  Highlights -100                      - the shoulder: the recorded top (+6) lands on Bianco (+2.5)
  3  Highlights -100 + Soft Clip 2.5      - the roof on top of it
  4  Shadows +100, Blacks -67             - shadows up 2 stops, the black foot held
  5  Contrast +50                         - slope x1.4 at grey, bounded ends
  6  Kodak 2383 print emulation           - the measured reference, when Resolve's LUT is installed
  7  bright skin, 0 to +5 stops, as 2     - must not go flat pink
  8  blue sky, 0 to +6 stops, as 2        - drifts to white without turning purple

Everything runs the Python reference of the plugin (tests/model/tone.py), so the chart cannot drift.
"""
import math
import os
import struct
import sys
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import develop_model as dm  # noqa: E402
from model import tone as T  # noqa: E402

SG3C = 8
WIDTH, STRIP, GAP = 960, 96, 8
EV_LO, EV_HI = -8.0, 8.0
SKIN, SKY = (0.29, 0.20, 0.155), (0.06, 0.12, 0.30)
LUT_PATH = ('/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT/'
            'Film Looks/Rec709 Kodak 2383 D65.cube')


def display(lin):
    """Display code from a display-linear value, for the PNG."""
    return max(0.0, min(1.0, lin)) ** (1 / 2.2)


PANELS = {1: {'toneHighlights': -100}, 2: {'toneHighlights': -100, 'softClip': 1},
          3: {'toneShadows': 100, 'toneBlacks': -67}, 4: {'toneContrast': 50},
          6: {'toneHighlights': -100}, 7: {'toneHighlights': -100}}


def toned(rgb, panel):
    """S-Gamut3.Cine linear through the v5 tone stage, out as Rec.709 linear."""
    p = T.set_tone(panel, 1, True)
    xyz = dm.mul(dm.MATS[SG3C][0], rgb)
    if T.active(p):
        xyz = T.tone5(xyz, p)
    return dm.mul(dm.MATS[1][1], xyz)


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
                if mode < 6:
                    ev = EV_LO + (EV_HI - EV_LO) * f
                    lin = 0.18 * 2 ** ev
                    if mode == 0:
                        c = [display(lin)] * 3
                    elif mode == 5:
                        c = ([lut_neutral(lut[0], lut[1], cineon(lin))] * 3 if lut else [0.12, 0.12, 0.14])
                    else:
                        c = [display(v) for v in toned([lin] * 3, PANELS[mode])]
                else:
                    base, top = (SKIN, 5.0) if mode == 6 else (SKY, 6.0)
                    c = [display(v) for v in toned([v * 2 ** (top * f) for v in base], PANELS[mode])]
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
        print('nota: il LUT Kodak 2383 non e installato, la sesta striscia resta vuota')
    rows = strips(lut)
    write_png(path, rows, WIDTH)
    print('written %s (%dx%d)' % (path, WIDTH, len(rows)))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
