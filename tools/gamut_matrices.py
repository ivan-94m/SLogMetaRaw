# SPDX-License-Identifier: GPL-3.0-or-later
"""Compute RGB<->XYZ(D65) matrices for the DCTL gamuts (Bradford-adapted to D65)."""
def inv(m):
    d = (m[0][0]*(m[1][1]*m[2][2]-m[1][2]*m[2][1]) - m[0][1]*(m[1][0]*m[2][2]-m[1][2]*m[2][0])
         + m[0][2]*(m[1][0]*m[2][1]-m[1][1]*m[2][0]))
    return [[(m[(j+1)%3][(i+1)%3]*m[(j+2)%3][(i+2)%3]-m[(j+1)%3][(i+2)%3]*m[(j+2)%3][(i+1)%3])/d
             for j in range(3)] for i in range(3)]
def mm(a, b): return [[sum(a[i][k]*b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
def mv(a, v): return [sum(a[i][k]*v[k] for k in range(3)) for i in range(3)]
def xyz(c): x, y = c; return [x/y, 1.0, (1-x-y)/y]
def rgb2xyz(r, g, b, w):
    M = [[xyz(r)[i], xyz(g)[i], xyz(b)[i]] for i in range(3)]
    S = mv(inv(M), xyz(w))
    return [[M[i][j]*S[j] for j in range(3)] for i in range(3)]
BR = [[0.8951, 0.2664, -0.1614], [-0.7502, 1.7135, 0.0367], [0.0389, -0.0685, 1.0296]]
def cat(ws, wd):
    s, d = mv(BR, xyz(ws)), mv(BR, xyz(wd))
    return mm(inv(BR), mm([[d[0]/s[0], 0, 0], [0, d[1]/s[1], 0], [0, 0, d[2]/s[2]]], BR))
D65, D60, DCI = (0.3127, 0.3290), (0.32168, 0.33767), (0.314, 0.351)
SPACES = [  # order = DCTL codes = order of the "Color Space" menu
    ('DWG',   (0.8000, 0.3130), (0.1682, 0.9877), (0.0790, -0.1155), D65),
    ('709',   (0.640, 0.330), (0.300, 0.600), (0.150, 0.060), D65),
    ('2020',  (0.708, 0.292), (0.170, 0.797), (0.131, 0.046), D65),
    ('P3D65', (0.680, 0.320), (0.265, 0.690), (0.150, 0.060), D65),
    ('P3D60', (0.680, 0.320), (0.265, 0.690), (0.150, 0.060), D60),
    ('P3DCI', (0.680, 0.320), (0.265, 0.690), (0.150, 0.060), DCI),
    ('SG',    (0.730, 0.280), (0.140, 0.855), (0.100, -0.050), D65),
    ('SG3',   (0.730, 0.280), (0.140, 0.855), (0.100, -0.050), D65),
    ('SG3C',  (0.766, 0.275), (0.225, 0.800), (0.089, -0.087), D65),
    ('AP0',   (0.7347, 0.2653), (0.0, 1.0), (0.0001, -0.0770), D60),
    ('AP1',   (0.713, 0.293), (0.165, 0.830), (0.128, 0.044), D60),
]
def matrices():
    out = []
    for name, r, g, b, w in SPACES:
        m = rgb2xyz(r, g, b, w)
        if w != D65:
            m = mm(cat(w, D65), m)
        out.append((name, m, inv(m)))
    return out
if __name__ == '__main__':
    for name, m, mi in matrices():
        print(name, [round(v, 6) for row in m for v in row], 'white->', [round(v, 5) for v in mv(m, [1, 1, 1])])
