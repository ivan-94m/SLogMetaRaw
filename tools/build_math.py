# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate ofx/SLogMetaRaw/DevelopMath.h from DevelopMath.h.in (matrices from tools/gamut_matrices.py)."""
import os

from gamut_matrices import matrices

HERE = os.path.dirname(os.path.abspath(__file__))
OFX_DIR = os.path.join(os.path.dirname(HERE), 'ofx', 'SLogMetaRaw')


def f(v):
    """Float literal valid in C++ and Metal: always has a decimal point ('0.0f', never '0f')."""
    s = ('%.9f' % v).rstrip('0')
    if s.endswith('.'):
        s += '0'
    if s in ('-0.0', '0.0'):
        s = '0.0'
    return s + 'f'


def c_array(name, idx):
    rows = []
    for code, (sp, m, mi) in enumerate(matrices()):
        mat = m if idx == 0 else mi
        rows.append('    ' + ', '.join(f(v) for r in mat for v in r) + ',  // %d %s' % (code, sp))
    return 'SM_CONST float %s[%d] = {\n%s\n};' % (name, 9 * len(rows), '\n'.join(rows))


if __name__ == '__main__':
    src = open(os.path.join(OFX_DIR, 'DevelopMath.h.in')).read()
    out = src.replace('{{MATRICES}}', c_array('SM_RGB_TO_XYZ', 0) + '\n' + c_array('SM_XYZ_TO_RGB', 1))
    open(os.path.join(OFX_DIR, 'DevelopMath.h'), 'w').write(out)
    print('written', os.path.join(OFX_DIR, 'DevelopMath.h'))
