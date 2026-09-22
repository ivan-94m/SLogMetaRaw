# SPDX-License-Identifier: GPL-3.0-or-later
"""The Metal kernel of SLogMetaRaw (compiled at runtime, like Resolve does) must match the CPU path."""
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OFX = os.path.join(ROOT, 'ofx', 'SLogMetaRaw')


class Metal(unittest.TestCase):
    def test_kernel_matches_cpu(self):
        if platform.system() != 'Darwin':
            self.skipTest('Metal e il suo framework esistono solo su macOS')
        if not shutil.which('clang++') or not os.path.exists(os.path.join(OFX, 'DevelopMathSource.inc')):
            self.skipTest('build the plugin first (make in ofx/SLogMetaRaw)')
        tmp = tempfile.mkdtemp()
        try:
            exe = os.path.join(tmp, 'metal_test')
            subprocess.run(['clang++', '-std=c++17', '-fno-objc-arc', '-O2', '-I', OFX,
                            os.path.join(ROOT, 'tests', 'metal_test.mm'), os.path.join(OFX, 'MetalKernel.mm'),
                            '-framework', 'Metal', '-framework', 'Foundation', '-o', exe],
                           check=True, capture_output=True)
            out = subprocess.run([exe], capture_output=True, text=True).stdout.strip()
            if out == 'NO_DEVICE':
                self.skipTest('no Metal device')
            self.assertTrue(out.startswith('MAXDIFF'), out)
            self.assertLess(float(out.split()[1]), 2e-4)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()


METAL_BRANCH_MAIN = """
// Compile DevelopMath.h through its METAL branch. The Metal dialect is C++14 with a
// few keywords and a maths library that overloads the same names, so mapping those
// and defining __METAL_VERSION__ type-checks the branch Resolve compiles at runtime -
// the branch no other test on a non-Apple machine can reach, and the one where a
// construct that only C++ accepts would go unnoticed until a user hit it.
#include <cmath>
using std::pow; using std::log2; using std::log10; using std::exp2;
using std::fmax; using std::fmin;
#define __METAL_VERSION__ 230
#define constant const   // address space qualifier; const alone works in both uses
#include "DevelopMath.h"
int main() {
    DevelopParams p = {};
    p.eTop = sm_tank_top(9);
    p.highlights = -1.0f;
    p.shadows = 1.0f;
    p.chromaRecover = -1.0f;
    SMf3 o = sm_develop(smf3(0.5f, 0.4f, 0.3f), p);
    return (o.x == o.x && o.y == o.y && o.z == o.z) ? 0 : 1;
}
"""


class SharedHeader(unittest.TestCase):
    """The header is compiled three times over: as C++ in the plugin, as Metal in the
    kernel, and as a C string embedded in the binary. These run anywhere."""

    def test_the_metal_branch_compiles(self):
        if not shutil.which('clang++'):
            self.skipTest('clang++ non disponibile')
        tmp = tempfile.mkdtemp()
        try:
            src = os.path.join(tmp, 'metal_branch.cpp')
            exe = os.path.join(tmp, 'metal_branch')
            with open(src, 'w', encoding='utf-8') as fh:
                fh.write(METAL_BRANCH_MAIN)
            r = subprocess.run(['clang++', '-std=c++17', '-Wall', '-Werror', '-O2',
                                '-I', OFX, '-o', exe, src], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(subprocess.run([exe]).returncode, 0)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_the_embedded_source_matches_the_header(self):
        """MetalKernel.mm compiles kDevelopMathSource, not the file. If the two drift
        the CPU path and the GPU path silently run different maths."""
        inc = os.path.join(OFX, 'DevelopMathSource.inc')
        if not os.path.exists(inc):
            self.skipTest('DevelopMathSource.inc non generato')
        with open(inc, encoding='utf-8') as fh:
            lines = re.findall(r'^\s*"(.*)\\n";?$', fh.read(), re.M)
        rebuilt = '\n'.join(l.replace('\\"', '"').replace('\\\\', '\\') for l in lines) + '\n'
        with open(os.path.join(OFX, 'DevelopMath.h'), encoding='utf-8') as fh:
            self.assertEqual(rebuilt, fh.read(),
                             'rigenera: python3 ofx/SLogMetaRaw/embed_source.py '
                             'ofx/SLogMetaRaw/DevelopMath.h ofx/SLogMetaRaw/DevelopMathSource.inc')

    def test_the_header_matches_its_template(self):
        """DevelopMath.h is generated. An edit made to it directly is lost the next
        time make runs, so it must already equal what the generator produces."""
        with open(os.path.join(OFX, 'DevelopMath.h'), encoding='utf-8') as fh:
            before = fh.read()
        subprocess.run([sys.executable, 'build_math.py'],
                       cwd=os.path.join(ROOT, 'tools'), check=True, capture_output=True)
        with open(os.path.join(OFX, 'DevelopMath.h'), encoding='utf-8') as fh:
            self.assertEqual(before, fh.read(),
                             'DevelopMath.h e stato modificato a mano: le modifiche '
                             'vanno in DevelopMath.h.in')
