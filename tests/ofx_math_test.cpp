// SPDX-License-Identifier: GPL-3.0-or-later
// Runs gen/DevelopMath.h on the cases read from stdin (one per line) for tests/test_ofx_math.py.
//   default:     r g b nodeSpace nodeGamma outSpace outGamma shotK shotTint shotEI k tint ei
//                levelFix levelSpace levelGamma levelGain levelOffset fcMode fcU fcV fcKu fcKv fcTu fcTv TONE
//                -> the developed pixel
//   --dump-tone: outSpace convert expo TONE -> every tone field sm_set_tone writes
//   --curve lo hi n: expo TONE -> n + 1 lines "e d hl hw" of sm_t5_curve at e = lo..hi (float32), then "end"
//   --fma a b c: a*b+c, exactly 0 for the probe values only without contraction
// TONE = contrast highlights shadows whites blacks vibrance saturation zonePivot zoneExp[4] zoneSat[4]
//        zoneRange[4] zoneFalloff[4] softClip softClipLevel softClipColor   (27 values)
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <sstream>
#include <string>
#include <vector>

#include "gen/DevelopMath.h"

static const size_t kToneValues = 27;

static SMToneControls tone(const double* v)
{
    SMToneControls c = sm_tone_defaults();
    c.contrast = v[0]; c.highlights = v[1]; c.shadows = v[2]; c.whites = v[3];
    c.blacks = v[4]; c.vibrance = v[5]; c.saturation = v[6]; c.zonePivot = v[7];
    for (int z = 0; z < 4; ++z) {
        c.zoneExp[z] = v[8 + z];
        c.zoneSat[z] = v[12 + z];
        c.zoneRange[z] = v[16 + z];
        c.zoneFalloff[z] = v[20 + z];
    }
    c.softClip = (int)v[24];
    c.softClipLevel = v[25];
    c.softClipColor = v[26];
    return c;
}

static void printArray(const char* name, const float* a, int n)
{
    printf("%s", name);
    for (int i = 0; i < n; ++i) printf(" %.9g", a[i]);
    printf("\n");
}

static void dumpTone(const DevelopParams& p)
{
    printf("toneOn %d\nblkA %.9g\nblkRenorm %.9g\nconC %.9g\nconPivot %.9g\n", p.toneOn, p.blkA, p.blkRenorm,
           p.curve.conC, p.curve.conPivot);
    printf("hlE %.9g\nhlStart %.9g\n", p.curve.hlE, p.curve.hlStart);
    printArray("zoneE", p.curve.zoneE, SM_T5_SLOTS);
    printArray("zoneEdge", p.curve.zoneEdge, SM_T5_SLOTS);
    printArray("zoneK", p.curve.zoneK, SM_T5_SLOTS);
    printArray("zoneFill", p.curve.zoneFill, SM_T5_SLOTS);
    printf("roofOn %d\nroofStops %.9g\nroofRenorm %.9g\nroofPurity %.9g\nroofLin %.9g\n", p.curve.roofOn,
           p.curve.roofStops, p.curve.roofRenorm, p.roofPurity, p.roofLin);
    printf("hlAmount %.9g\nhlWhiteLin %.9g\nhlTaperSpace %d\n", p.hlAmount, p.hlWhiteLin, p.hlTaperSpace);
    printf("colorOn %d\nrefSpace %d\nsat %.9g\nvib %.9g\n", p.colorOn, p.refSpace, p.sat, p.vib);
    printArray("zSat", p.zSat, 4);
    printArray("zNomEdge", p.zNomEdge, 4);
    printArray("zNomInvF", p.zNomInvF, 4);
    printf("end\n");
}

int main(int argc, char** argv)
{
    if (argc == 5 && !strcmp(argv[1], "--fma")) {
        volatile float a = strtof(argv[2], nullptr), b = strtof(argv[3], nullptr), c = strtof(argv[4], nullptr);
        printf("%.10g\n", a * b + c);
        return 0;
    }
    const bool dump = argc == 2 && !strcmp(argv[1], "--dump-tone");
    const bool curve = argc == 5 && !strcmp(argv[1], "--curve");
    std::string line;
    char buf[8192];
    while (fgets(buf, sizeof(buf), stdin)) {
        std::istringstream in(buf);
        std::vector<double> v;
        double x;
        while (in >> x) v.push_back(x);
        if (dump) {
            if (v.size() != 3 + kToneValues) continue;
            DevelopParams p = {};
            const SMToneControls c = tone(&v[3]);
            sm_set_tone(&p, &c, (int)v[0], (int)v[1], v[2]);
            dumpTone(p);
            continue;
        }
        if (curve) {
            if (v.size() != 1 + kToneValues) continue;
            DevelopParams p = {};
            const SMToneControls c = tone(&v[1]);
            sm_set_tone(&p, &c, SM_T5_REF, 0, v[0]);
            const double lo = atof(argv[2]), hi = atof(argv[3]);
            const int n = atoi(argv[4]);
            for (int i = 0; i <= n; ++i) {
                const float e = (float)(lo + (hi - lo) * i / n);
                const SMToneOut o = sm_t5_curve(e, p.curve);
                printf("%.9g %.9g %.9g %.9g\n", e, o.d, o.hl, o.hw);
            }
            printf("end\n");
            continue;
        }
        if (v.size() != 25 + kToneValues) continue;
        DevelopParams p = {};
        p.nodeSpace = (int)v[3]; p.nodeGamma = (int)v[4]; p.outSpace = (int)v[5]; p.outGamma = (int)v[6];
        p.convert = (p.outSpace != p.nodeSpace || p.outGamma != p.nodeGamma) ? 1 : 0;
        p.expo = (float)(v[12] / v[9]);
        sm_set_white_balance(&p, v[7], v[8], v[10], v[11]);
        p.levelFix = (int)v[13]; p.levelSpace = (int)v[14]; p.levelGamma = (int)v[15];
        p.levelGain = (float)v[16]; p.levelOffset = (float)v[17];
        p.fcMode = (int)v[18];
        p.fcU = (float)v[19]; p.fcV = (float)v[20]; p.fcKu = (float)v[21]; p.fcKv = (float)v[22];
        p.fcTu = (float)v[23]; p.fcTv = (float)v[24];
        const SMToneControls c = tone(&v[25]);
        sm_set_tone(&p, &c, p.outSpace, p.convert, p.expo);
        SMf3 o = sm_develop(smf3((float)v[0], (float)v[1], (float)v[2]), p);
        printf("%.9g %.9g %.9g\n", o.x, o.y, o.z);
    }
    return 0;
}
