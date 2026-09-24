// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "Params.h"
#include "Transfer.h"
#include "Gamut.h"
#include "Tone.h"

// Measuring views, taken after exposure and white balance and before every trim, so each
// answers only to its own control (docs/FALSE_COLOR.md).

SM_FN SMf3 sm_fc_exposure(float ev) {
    if (ev >= 5.5f) return smf3(0.96f, 0.16f, 0.10f);                    // clipped
    if (ev >= 4.0f) return smf3(1.00f, 0.88f, 0.12f);                    // a stop from clip
    if (ev >= 0.70f && ev <= 1.30f) return smf3(1.00f, 0.56f, 0.72f);    // skin, one stop over grey
    if (ev >= -0.33f && ev <= 0.33f) return smf3(0.13f, 0.82f, 0.20f);   // 18% grey
    if (ev <= -6.0f) return smf3(0.42f, 0.12f, 0.62f);                   // black clip
    if (ev <= -4.0f) return smf3(0.10f, 0.28f, 0.88f);                   // deep shadow
    float g = sm_clamp((ev + 6.0f) / 11.5f, 0.06f, 0.92f);
    return smf3(g, g, g);
}

// HSL -> RGB (display values): the white-balance views paint canonical hues like CineMatch.
SM_FN float sm_hsl_channel(float p, float q, float t) {
    t = t - floor(t);
    if (t < 1.0f / 6.0f) return p + (q - p) * 6.0f * t;
    if (t < 0.5f) return q;
    if (t < 2.0f / 3.0f) return p + (q - p) * (2.0f / 3.0f - t) * 6.0f;
    return p;
}
SM_FN SMf3 sm_hsl_rgb(float h, float s, float l) {
    float q = l < 0.5f ? l * (1.0f + s) : l + s - l * s;
    float p = 2.0f * l - q;
    return smf3(sm_hsl_channel(p, q, h + 1.0f / 3.0f), sm_hsl_channel(p, q, h), sm_hsl_channel(p, q, h - 1.0f / 3.0f));
}

// Temperature (2) and tint (3): the picture in grey; a pixel is coloured only when its cast lies on this
// slider's axis (orange/blue, green/magenta), with its saturation boosted up to 8x near neutral as
// CineMatch does, faded out where the pixel is too dark or too bright to carry a hue. The axis comes
// from the sliders' own response (sm_fc_calibrate), so grey means "this slider is right here".
SM_FN SMf3 sm_fc_balance(SMf3 xyz, SM_CREF(DevelopParams) p, float ev, float mono) {
    float d = xyz.x + 15.0f * xyz.y + 3.0f * xyz.z;
    SMf3 rgb = sm_from_xyz(xyz, 1);
    rgb = smf3(SM_MAX(rgb.x, 0.0f), SM_MAX(rgb.y, 0.0f), SM_MAX(rgb.z, 0.0f));
    float mx = SM_MAX(rgb.x, SM_MAX(rgb.y, rgb.z)), mn = SM_MIN(rgb.x, SM_MIN(rgb.y, rgb.z));
    if (d < 1e-9f || mx <= 0.0f) return smf3(mono, mono, mono);
    float du = 4.0f * xyz.x / d - p.fcU, dv = 6.0f * xyz.y / d - p.fcV;
    float kelvin = -(p.fcKu * du + p.fcKv * dv) / 100.0f;   // > 0: reads cool, wants warming
    float tint = -(p.fcTu * du + p.fcTv * dv) / 5.0f;       // > 0: reads green
    if ((SM_ABS(kelvin) >= SM_ABS(tint)) != (p.fcMode == 2)) return smf3(mono, mono, mono);
    float lo = SM_POW(mn / mx, 1.0f / 2.2f);   // display-encoded and normalised: exposure does not matter
    float r = (1.0f - lo) / (1.0f + lo);
    float sat = sm_clamp(r * (8.0f - 7.0f * r), 0.0f, 1.0f)
              * sm_clamp((ev + 6.0f) / 2.0f, 0.0f, 1.0f) * sm_clamp(5.5f - ev, 0.0f, 1.0f);
    float hue = p.fcMode == 2 ? (kelvin > 0.0f ? 0.586f : 0.08f) : (tint > 0.0f ? 0.30f : 0.85f);
    return sm_hsl_rgb(hue, sat, mono);
}

// Zone view tints (display Rec.709, gamma 2.2): Black, Shadow, Light, Specular.
SM_CONST float SM_FC_ZONE_TINT[12] = { 0.00f, 0.47f, 0.55f, 0.93f, 0.28f, 0.80f,
                                       1.00f, 0.55f, 0.05f, 0.55f, 1.00f, 0.95f };

// fcMode 4: each zone tints by its nominal weight on the stops the zones read; the rest is grey.
SM_FN SMf3 sm_fc_zones(SMf3 xyz, SM_CREF(DevelopParams) p) {
    float n = sm_t5_norm(sm_from_xyz(xyz, SM_T5_REF));
    float e = sm_t5_log(n * SM_EXP2(sm_t5_blacks(n, p.blkA, p.blkRenorm)));
    SMf3 out = smf3(0.0f, 0.0f, 0.0f);
    float s = 0.0f;
    for (int z = 0; z < 4; ++z) {
        float w = sm_t5_zone_weight(e, z, p);
        s += w;
        out = smf3(out.x + w * SM_FC_ZONE_TINT[z * 3], out.y + w * SM_FC_ZONE_TINT[z * 3 + 1],
                   out.z + w * SM_FC_ZONE_TINT[z * 3 + 2]);
    }
    if (s >= 1.0f) return smf3(out.x / s, out.y / s, out.z / s);
    float mono = sm_clamp((e + 6.0f) / 11.5f, 0.06f, 0.92f) * (1.0f - s);
    return smf3(out.x + mono, out.y + mono, out.z + mono);
}

SM_FN SMf3 sm_false_color(SMf3 xyz, SM_CREF(DevelopParams) p) {
    if (p.fcMode == 4) return sm_fc_zones(xyz, p);
    float y = xyz.y > 1e-9f ? xyz.y : 1e-9f;
    float ev = SM_LOG2(y / 0.18f);
    if (p.fcMode == 1) return sm_fc_exposure(ev);
    return sm_fc_balance(xyz, p, ev, sm_clamp((ev + 6.0f) / 11.5f, 0.06f, 0.92f));
}

// The palette is a display colour: take it back to linear Rec.709 and re-encode it in the
// space the node writes, so the bands look the same whatever the timeline works in.
SM_FN SMf3 sm_fc_emit(SMf3 c, SM_CREF(DevelopParams) p) {
    int space = p.convert != 0 ? p.outSpace : p.nodeSpace;
    int gamma = p.convert != 0 ? p.outGamma : p.nodeGamma;
    SMf3 lin = smf3(sm_decode(c.x, 2), sm_decode(c.y, 2), sm_decode(c.z, 2));
    SMf3 o = sm_from_xyz(sm_to_xyz(lin, 1), space);
    return smf3(sm_encode(o.x, gamma), sm_encode(o.y, gamma), sm_encode(o.z, gamma));
}
