# SPDX-License-Identifier: GPL-3.0-or-later
"""Turn DevelopMath.h into a C string (kDevelopMathSource) for the runtime-compiled Metal kernel."""
import sys

src = open(sys.argv[1], encoding='utf-8').read()
lines = ['static const char* kDevelopMathSource =']
for line in src.splitlines():
    esc = line.replace('\\', '\\\\').replace('"', '\\"')
    lines.append('    "%s\\n"' % esc)
lines[-1] += ';'
open(sys.argv[2], 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
