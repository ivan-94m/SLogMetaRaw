// SPDX-License-Identifier: GPL-3.0-or-later
// The Detail pipeline on the CPU, free of OpenFX so the tests can run it on their own.
#pragma once
#include <cstddef>
#include <functional>
#include <vector>

#include "../../gen/DevelopMath.h"

// parallel(n, fn) runs fn(begin, end) over [0, n), split among threads; fn must only write its own rows.
using Parallel = std::function<void(int n, const std::function<void(int begin, int end)>& fn)>;

struct DetailScratch
{
    std::vector<float> L0, L, xa, J, tmp, Gg, G1;                     // full size
    std::vector<float> Lw, aB, bB, Dg, a2, b2, a3, b3, g0, g1, g2, g3;   // working grid
    std::vector<float> ch[3], E, at, bt, Lt, G2;                      // Dehaze grid, texture grid
};

struct DetailPlanes   // intermediate results, for the parity tests
{
    std::vector<float> L, B, Dg, G;
};

void detailRenderCPU(const DetailParams& p, const float* src, size_t srcRowFloats, float* dst, size_t dstRowFloats,
                     const Parallel& parallel, DetailScratch& s, DetailPlanes* planes = nullptr);
