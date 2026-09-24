// SPDX-License-Identifier: GPL-3.0-or-later
// Plain C shared by the CPU build and the runtime-compiled Metal kernels.
#pragma once

#ifdef __METAL_VERSION__
#define SM_FN inline
#define SM_CONST constant
#define SM_CPTR constant float*
#define SM_CREF(T) constant T&
// Metal's default math functions stay fast even under MTLMathModeSafe: parity needs precise::.
#define SM_POW precise::pow
#define SM_LOG2 precise::log2
#define SM_LOG10 precise::log10
#define SM_EXP2 precise::exp2
#define SM_EXP precise::exp
#define SM_TANH precise::tanh
#define SM_SQRT precise::sqrt
#define SM_ATAN2 precise::atan2
#define SM_MAX fmax
#define SM_MIN fmin
#define SM_ABS fabs
#else
#include <math.h>
#define SM_FN static inline
#define SM_CONST static const
#define SM_CPTR const float*
#define SM_CREF(T) const T&
#define SM_POW powf
#define SM_LOG2 log2f
#define SM_LOG10 log10f
#define SM_EXP2 exp2f
#define SM_EXP expf
#define SM_TANH tanhf
#define SM_SQRT sqrtf
#define SM_ATAN2 atan2f
#define SM_MAX fmaxf
#define SM_MIN fminf
#define SM_ABS fabsf
#endif

struct SMf3 { float x; float y; float z; };

SM_FN SMf3 smf3(float x, float y, float z) { SMf3 r; r.x = x; r.y = y; r.z = z; return r; }
SM_FN float sm_clamp(float v, float a, float b) { return SM_MIN(SM_MAX(v, a), b); }
