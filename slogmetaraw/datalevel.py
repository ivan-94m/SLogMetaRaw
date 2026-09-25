# SPDX-License-Identifier: GPL-3.0-or-later
"""Data level (code range) of a Sony clip, and the correction the node must apply.

Why this module exists
----------------------
Every transfer function is defined on a *scale*, and there are two in use:

  full  (data, "0-1023")   normalised value 0.0 = code 0,  1.0 = code 1023
  video (legal, "64-940")  normalised value 0.0 = code 64, 1.0 = code 940

Sony's S-Log curves are published on the **full** scale: S-Log3 black is code 95,
18% grey code 420, 90% white code 598; S-Log2 and S-Log put black at code 90
(Sony, "Technical Summary for S-Gamut3.Cine/S-Log3 and S-Gamut3/S-Log3", FAQ Q4:
*"S-Log3 is recorded as Full range in XAVC, MPEG and HDCAM SR File"*, and there is
no legal-range option in the camera). Broadcast curves — Rec.709, the Hypergammas,
Cine1-4, S-Cinetone, HLG — are the opposite: they are legal-anchored, 0 IRE = code
64, 100 IRE = code 940, with the headroom above 940 used for super-whites.

DaVinci Resolve scales every clip into its 32-bit float pipeline according to the
clip's *Data Level* attribute, **before** the node graph and before the Resolve
Colour Management input transform. So the image an OpenFX node receives is

    Data Level = Full   ->  x = CV / 1023
    Data Level = Video  ->  x = (CV - 64) / 876

and OpenFX has no property that says which one happened (checked against the
whole OFX 1.4/1.5 header set shipped with Resolve, including ofxColour.h: the
colour-management API cannot express signal range). Resolve's own manual only
says that *Auto* decides "based on the codec of the source media" — no flags, no
per-camera table. When it picks the wrong one for an S-Log clip the log decode
downstream is fed a mis-scaled curve, and the error is largest in the shadows.

``host`` is Resolve's own clip attribute ('Auto' | 'Full' | 'Video'). While it is
'Auto' the resolved scale is not observable from any API, so nothing is corrected
and the script sets it explicitly.

References for the tables below are collected in docs/DATA_LEVELS.md.
"""

FULL = 'Full'
VIDEO = 'Video'
AUTO = 'Auto'

# The two scales, in 10-bit code values. Every other bit depth is the same
# fractions of full scale, so one set of numbers covers 8, 10, 12 and 16 bit.
CV_MAX = 1023.0
CV_BLACK = 64.0          # 0 IRE on the video scale
CV_WHITE = 940.0         # 100 IRE on the video scale
CV_SPAN = CV_WHITE - CV_BLACK   # 876


def remap(src, dst):
    """(gain, offset) mapping a normalised value from the src scale to the dst scale.

    >>> remap(VIDEO, FULL)      # (CV-64)/876  ->  CV/1023
    (0.8563049853372434, 0.06256109481915933)
    >>> remap(FULL, VIDEO)
    (1.1678082191780822, -0.0730593607305936)
    """
    if src == dst or not src or not dst:
        return 1.0, 0.0
    if src == VIDEO:
        return CV_SPAN / CV_MAX, CV_BLACK / CV_MAX
    return CV_MAX / CV_SPAN, -CV_BLACK / CV_SPAN


# --- 1. which scale a capture gamma is defined on ----------------------------
# Names are the ones rtmd.GAMMA produces (RTMD 0x3210, Catalyst Browse labels).
# Anything not listed here is a legal-anchored broadcast curve -> VIDEO.
FULL_SCALE_GAMMAS = {
    'S-Log',                    # Sony: black code 90 (3.0 IRE)
    'S-Log2',                   # Sony: black code 90, and up to 104 IRE recorded
    'S-Gamut3/S-Log3',          # Sony: black code 95 (3.5 IRE), clips near 94 IRE
    'S-Gamut3.Cine/S-Log3',
    'FS-Log',
    'Cine-Log',
    'ACESproxy',
    'ACEScct',
    'Scene Linear',
}
# Sony NRT XML <Item name="CaptureGammaEquation"> values (lower case in the file).
FULL_SCALE_XML_GAMMAS = {'s-log', 's-log2', 's-log3', 's-log3-cine', 'slog', 'slog2', 'slog3',
                         'aces', 'acescct', 'acesproxy', 'scene-linear', 'cine-log'}

# Curves worth naming in the note because they are the usual source of confusion:
# they are legal range *with* super-whites, which Resolve cannot express at all
# (it has Video and Full, no "extended video").
SUPER_WHITE_GAMMAS = {
    'Cine1': 109, 'Cine3': 109, 'Cine4': 109, 'ITU-R BT.709-5': 109, 'Standard': 109,
    'Still': 109, 'R709 180%': 109, 'R709 800%': 109,
    'HG4609G33': 109, 'HG3259G40': 109, 'HG8009G40': 109, 'HG8009G33': 109,
    'HG8000G36': 109, 'HG3250G36': 109,
    'Cine2': 100, 'HG4600G30': 100, 'HG8000G30': 100,
}


def gamma_scale(gamma, xml_gamma=None):
    """FULL or VIDEO: the scale this capture gamma's transfer function is defined on."""
    if gamma:
        if gamma in FULL_SCALE_GAMMAS:
            return FULL
        if '/S-Log' in gamma or gamma.startswith('S-Log'):
            return FULL           # any future S-Log naming
    if xml_gamma and str(xml_gamma).strip().lower() in FULL_SCALE_XML_GAMMAS:
        return FULL
    if gamma or xml_gamma:
        return VIDEO
    return None


def required_level(meta):
    """(level, why) - the scale the clip's content is on, from its capture gamma."""
    gamma = meta.get('capture_gamma')
    xml_gamma = meta.get('xml_gamma')
    level = gamma_scale(gamma, xml_gamma)
    name = gamma or xml_gamma or '?'
    if level == FULL:
        return FULL, ('%s: curva definita su code value non scalati '
                      '(nero al codice 95 per S-Log3, 90 per S-Log2/S-Log)' % name)
    if level == VIDEO:
        sw = SUPER_WHITE_GAMMAS.get(gamma)
        why = '%s: curva ancorata al range legale (0 IRE = codice 64)' % name
        if sw:
            why += ', con super-white fino a %d%%' % sw
        return VIDEO, why
    return None, 'gamma di ripresa non registrata nel file'


# --- 2. what the file itself declares ---------------------------------------
# Sony writes the range in at most one of these places, and not always. Order is
# by authority: Sony's own per-clip acquisition metadata first, then the
# container/bitstream flags.

def _mxf_level(meta):
    """MXF CDCI reference levels -> FULL / VIDEO, using ffmpeg's mxf_get_color_range rule."""
    black = meta.get('mxf_black_ref')
    white = meta.get('mxf_white_ref')
    depth = meta.get('mxf_component_depth') or meta.get('v_bit_depth')
    if black is None or white is None or not depth or not 8 <= int(depth) <= 16:
        return None
    depth = int(depth)
    top = (1 << depth) - 1
    if black == 0 and white == top:
        return FULL
    if black == (1 << (depth - 4)) and white == (235 << (depth - 8)):
        return VIDEO
    # non-standard values: trust the black reference, it is the one that matters
    return FULL if black == 0 else VIDEO


def declared_level(meta):
    """(level, source) - what the file says about its own range, or (None, why not)."""
    lcr = meta.get('luminance_code_range')
    if isinstance(lcr, str) and 'full' in lcr.lower():
        return FULL, 'metadata Sony di acquisizione (RTMD 0x8120: %s)' % lcr
    if isinstance(lcr, str) and ('legal' in lcr.lower() or 'video' in lcr.lower()):
        return VIDEO, 'metadata Sony di acquisizione (RTMD 0x8120: %s)' % lcr
    mxf = _mxf_level(meta)
    if mxf:
        return mxf, ('descrittore immagine MXF (nero %s, bianco %s su %s bit)'
                     % (meta.get('mxf_black_ref'), meta.get('mxf_white_ref'),
                        meta.get('mxf_component_depth')))
    if meta.get('container') == 'MXF':
        # In an MXF the SPS is located by scanning for a start code inside
        # interleaved essence, so a VUI flag read from it is not trustworthy
        # enough to declare the range; the picture descriptor above is.
        return None, 'MXF senza livelli di riferimento nel descrittore immagine'
    vui = meta.get('v_full_range')
    if vui is not None:
        return (FULL if vui else VIDEO), 'flag video_full_range_flag del codec (VUI)'
    colr = meta.get('v_colr_full_range')
    if colr is not None:
        return (FULL if colr else VIDEO), 'box colr/nclx del file MP4'
    return None, 'il file non dichiara il range (i decoder assumono video)'


# --- 3. what Resolve does ----------------------------------------------------

def auto_guess(meta):
    """(level, why) - best guess at what Resolve's "Auto" resolves to for this clip.

    Only ever a guess: the Resolve manual documents Auto as "determined based on
    the codec of the source media" and the resolved value is not exposed by the
    API. Used for information, never to drive a correction on its own.
    """
    declared, _src = declared_level(meta)
    if declared:
        return declared, 'se Resolve legge il flag del file'
    return VIDEO, 'nessun flag nel file: i codec video sono interpretati come video'


def decide(meta, host=AUTO, override_required=None):
    """Everything the node needs to correct (or not) the data level.

    meta              the ``meta`` dict of extract.read_clip
    host              the clip's Data Level in Resolve: 'Auto' | 'Full' | 'Video',
                      or None when it could not be read
    override_required forces the target scale (used by the node's manual control)

    Returns a dict with 'required', 'host', 'known', 'gain', 'offset', 'fix' and
    human-readable 'note' / 'detail'.
    """
    required, why = required_level(meta)
    if override_required:
        required, why = override_required, 'impostato a mano'
    declared, declared_src = declared_level(meta)
    host = host or AUTO
    known = host in (FULL, VIDEO)
    gain, offset = (remap(host, required) if (known and required) else (1.0, 0.0))
    fix = 1 if (gain != 1.0 or offset != 0.0) else 0

    out = {
        'required': required, 'required_why': why,
        'declared': declared, 'declared_source': declared_src,
        'host': host, 'known': known,
        'gain': gain, 'offset': offset, 'fix': fix,
    }
    if not required:
        out['note'] = 'gamma non nota: nessuna correzione'
    elif not known:
        guess, guess_why = auto_guess(meta)
        out['guess'] = guess
        out['note'] = ('Resolve e su Auto: il valore effettivo non e leggibile. '
                       'Serve %s (%s). Imposta Data Level = %s in Attributi clip '
                       '(o lascia che lo faccia lo script) e la correzione diventa esatta.'
                       % (required, guess_why, required))
    elif fix:
        direction = 'video -> full' if host == VIDEO else 'full -> video'
        out['note'] = ('Resolve interpreta questa clip come %s ma %s richiede %s: '
                       'correzione %s (x%.6f %+.6f) prima della decodifica log.'
                       % (host, meta.get('capture_gamma') or 'la gamma', required, direction,
                          gain, offset))
    else:
        out['note'] = 'Resolve interpreta questa clip come %s: corretto, nessuna correzione.' % host
    bits = ['richiesto %s' % (required or '?')]
    if declared:
        bits.append('dichiarato %s (%s)' % (declared, declared_src))
    bits.append('Resolve %s' % host)
    out['detail'] = ' · '.join(bits)
    if required and declared and required != declared:
        out['conflict'] = ('il file dichiara %s ma %s -> vale la gamma: Sony scrive '
                           'il flag in modo incoerente sui corpi consumer.' % (declared, why))
    return out


def summary(meta, host=AUTO):
    """One-line string for the clip table and the Camera Notes block."""
    d = decide(meta, host)
    txt = d['required'] or '?'
    if d['declared'] and d['declared'] != d['required']:
        txt += ' (file: %s)' % d['declared']
    if d['host'] and d['host'] != AUTO:
        txt += ' · Resolve: %s' % d['host']
        if d['fix']:
            txt += ' · da correggere'
    else:
        txt += ' · Resolve: Auto'
    return txt
