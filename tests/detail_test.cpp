// SPDX-License-Identifier: GPL-3.0-or-later
// Runs the Detail node's CPU pipeline (src/detail/DetailPasses.cpp) for tests/test_detail.py.
// stdin:  W H href base space gamma par threads
//         name=value ... (panel controls, one line)
//         W*H lines "r g b" (encoded input)
// stdout: W*H lines "r g b L B Dg G"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

#include "../ofx/SLogMetaRaw/src/detail/DetailPasses.h"

static void set(SMDetailControls& c, const std::string& name, double v)
{
    static const char* const zones[] = { "Black", "Shadow", "Light", "Specular" };
    std::map<std::string, double*> f = {
        { "localContrast", &c.localContrast }, { "localHighlights", &c.localHighlights },
        { "localShadows", &c.localShadows }, { "texture", &c.texture }, { "clarity", &c.clarity },
        { "dehaze", &c.dehaze }, { "localZonePivot", &c.zonePivot }, { "preserveDetail", &c.preserveDetail },
        { "detailRadius", &c.detailRadius }, { "edgeThreshold", &c.edgeThreshold },
        { "noiseThreshold", &c.noiseThreshold }, { "clarityCenter", &c.clarityCenter },
        { "hazeLevel", &c.hazeLevel }, { "hazeWarmth", &c.hazeWarmth }, { "localWhite", &c.localWhite } };
    for (int z = 0; z < 4; ++z) {
        f[std::string("localZone") + zones[z] + "Exp"] = &c.zoneExp[z];
        f[std::string("localZone") + zones[z] + "Range"] = &c.zoneRange[z];
        f[std::string("localZone") + zones[z] + "Falloff"] = &c.zoneFalloff[z];
    }
    if (name == "viewGain") c.viewGain = v != 0.0;
    else if (name == "viewBase") c.viewBase = v != 0.0;
    else if (f.count(name)) *f[name] = v;
    else { fprintf(stderr, "controllo sconosciuto %s\n", name.c_str()); exit(2); }
}

int main()
{
    int W, H, base, space, gamma, threads;
    double href, par;
    char line[4096];
    if (!fgets(line, sizeof(line), stdin)
        || sscanf(line, "%d %d %lf %d %d %d %lf %d", &W, &H, &href, &base, &space, &gamma, &par, &threads) != 8)
        return 2;
    if (!fgets(line, sizeof(line), stdin)) return 2;   // the controls, possibly none
    SMDetailControls c = sm_detail_defaults();
    std::istringstream in(line);
    std::string kv;
    while (in >> kv) {
        const size_t eq = kv.find('=');
        set(c, kv.substr(0, eq), atof(kv.substr(eq + 1).c_str()));
    }
    std::vector<float> src((size_t)W * H * 4), dst((size_t)W * H * 4);
    for (size_t i = 0; i < (size_t)W * H; ++i) {
        if (scanf("%f %f %f", &src[i * 4], &src[i * 4 + 1], &src[i * 4 + 2]) != 3) return 2;
        src[i * 4 + 3] = 1.0f;
    }
    DetailParams p;
    dt_prepare(&p, W, H, href, par, space, gamma, &c, base);
    Parallel parallel = [threads](int n, const std::function<void(int, int)>& fn) {
        if (threads <= 1) { fn(0, n); return; }
        std::vector<std::thread> pool;
        for (int t = 0; t < threads; ++t) pool.emplace_back(fn, n * t / threads, n * (t + 1) / threads);
        for (auto& th : pool) th.join();
    };
    DetailScratch scratch;
    DetailPlanes planes;
    detailRenderCPU(p, src.data(), (size_t)W * 4, dst.data(), (size_t)W * 4, parallel, scratch, &planes);
    for (size_t i = 0; i < (size_t)W * H; ++i)
        printf("%.9g %.9g %.9g %.9g %.9g %.9g %.9g\n", dst[i * 4], dst[i * 4 + 1], dst[i * 4 + 2], planes.L[i],
               planes.B[i], planes.Dg[i], planes.G[i]);
    return 0;
}
