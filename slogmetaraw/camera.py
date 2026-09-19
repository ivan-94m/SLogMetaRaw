# SPDX-License-Identifier: GPL-3.0-or-later
"""Camera colour and as-shot values used by the SLogMetaRaw plugin.

Codes match ofx/SLogMetaRaw/DevelopMath.h (gamut and transfer tables).
"""

SPACE_CODE = {'DaVinci WG': 0, 'Rec.709': 1, 'Rec.2020': 2, 'P3 D65': 3, 'P3 D60': 4, 'P3 DCI': 5,
              'S-Gamut': 6, 'S-Gamut3': 7, 'S-Gamut3.Cine': 8, 'ACES AP0': 9, 'ACES AP1': 10}
GAMMA_CODE = {'DaVinci Intermediate': 0, 'Linear': 1, 'Gamma 2.2': 2, 'Gamma 2.4': 3, 'Gamma 2.6': 4,
              'Rec.709': 5, 'sRGB': 6, 'SLog': 7, 'SLog2': 8, 'SLog3': 9, 'ACEScct': 10}
# nominal Kelvin for the Sony "Lighting preset" when the camera did not record 0x810E
PRESET_KELVIN = {'Daylight': 5600, 'Cloudy': 6500, 'Shade': 7500, 'Incandescent': 3200,
                 'Fluorescent': 4000}


class NotSupported(Exception):
    pass


def camera_space(meta):
    """(gamut, gamma) the camera recorded, as named in the Camera Raw menus."""
    cs = meta.get('color_space') or ''
    for prefix, gamut, gamma in (('S-Gamut3.Cine/S-Log3', 'S-Gamut3.Cine', 'SLog3'),
                                 ('S-Gamut3/S-Log3', 'S-Gamut3', 'SLog3'),
                                 ('S-Gamut/S-Log2', 'S-Gamut', 'SLog2'),
                                 ('S-Gamut/S-Log', 'S-Gamut', 'SLog')):
        if cs.startswith(prefix):
            return gamut, gamma
    raise NotSupported('Profilo "%s" non logaritmico: S-Log MetaRaw richiede S-Log2/S-Log3.' % cs)


def shot_values(meta):
    """As-shot (Kelvin, tint, EI, estimated_wb) from the clip metadata."""
    k = meta.get('white_balance_k')
    estimated = False
    if not k:
        k = PRESET_KELVIN.get(meta.get('lighting_preset'), 5600)
        estimated = True
    tint = meta.get('tint') or 0
    ei = meta.get('exposure_index') or meta.get('iso') or 800
    return int(k), float(tint), int(ei), estimated
