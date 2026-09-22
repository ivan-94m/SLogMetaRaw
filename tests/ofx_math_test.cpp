// SPDX-License-Identifier: GPL-3.0-or-later
// Reads test cases from stdin and prints the output of sm_develop (DevelopMath.h).
// Each line: r g b nodeSpace nodeGamma outSpace outGamma shotK shotTint shotEI k tint ei
//            shadows highlights contrast saturation boost
//            levelFix levelSpace levelGamma levelGain levelOffset
//            fcMode fcU fcV fcKu fcKv fcTu fcTv chromaRecover
#include <cstdio>
#include "../ofx/SLogMetaRaw/DevelopMath.h"

int main() {
    float r, g, b, shotK, shotT, shotEI, k, t, ei, sh, hi, co, sa, bo, lgain, loff;
    float fcu, fcv, fcku, fckv, fctu, fctv, chroma;
    int ns, ng, os, og, lfix, lspace, lgamma, fcm;
    while (scanf("%f %f %f %d %d %d %d %f %f %f %f %f %f %f %f %f %f %f %d %d %d %f %f"
                 " %d %f %f %f %f %f %f %f",
                 &r, &g, &b, &ns, &ng, &os, &og,
                 &shotK, &shotT, &shotEI, &k, &t, &ei, &sh, &hi, &co, &sa, &bo,
                 &lfix, &lspace, &lgamma, &lgain, &loff,
                 &fcm, &fcu, &fcv, &fcku, &fckv, &fctu, &fctv, &chroma) == 31) {
        DevelopParams p = {};
        p.nodeSpace = ns; p.nodeGamma = ng; p.outSpace = os; p.outGamma = og;
        p.convert = (os != ns || og != ng) ? 1 : 0;
        p.expo = ei / shotEI;
        sm_set_white_balance(&p, shotK, shotT, k, t);
        p.shadows = sh; p.highlights = hi; p.contrast = co; p.saturation = sa; p.boost = bo;
        p.eTop = sm_tank_top(ng);   // as buildParams does when the clip has no camera curve
        p.levelFix = lfix; p.levelSpace = lspace; p.levelGamma = lgamma;
        p.levelGain = lgain; p.levelOffset = loff;
        p.fcMode = fcm; p.fcU = fcu; p.fcV = fcv;
        p.fcKu = fcku; p.fcKv = fckv; p.fcTu = fctu; p.fcTv = fctv;
        p.chromaRecover = chroma;
        SMf3 o = sm_develop(smf3(r, g, b), p);
        printf("%.7f %.7f %.7f\n", o.x, o.y, o.z);
    }
    return 0;
}
