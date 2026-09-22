# SPDX-License-Identifier: GPL-3.0-or-later
"""Decoder for Sony acquisition metadata ('rtmd').

The same payload is stored per frame in XAVC MP4 files (a timed-metadata
track with a 0x1C-byte sample header) and in XAVC MXF files (split across
SMPTE ST 436 ANC packets, DID 0x43 / SDID 0x05). It is a series of KLV packs
keyed by SMPTE ULs (RDD 18 acquisition metadata sets), each holding local
tags (2-byte tag, 2-byte length).

Tag semantics: SMPTE RDD 18, ExifTool's Sony::rtmd table, telemetry-parser's
src/sony/rtmd_tags.rs (MIT, (c) AdrianEddy), and field-by-field comparison
with Sony Catalyst Browse. Labels and units follow Catalyst Browse. Unknown
tags are kept as raw hex so nothing is lost.
"""
import struct

UL_PREFIX = b'\x06\x0e\x2b\x34'

SET_NAMES = {
    '0c02010101010000': 'Lens',
    '0c02010102010000': 'Camera',
    '0c0201017f010000': 'Sony',
}

# --- UL value tables (labels as shown by Catalyst Browse where known) --------

GAMMA = {
    0x01010000: 'ITU-R BT.470', 0x01020000: 'ITU-R BT.709-5', 0x01030000: 'SMPTE ST 240',
    0x01040000: 'SMPTE ST 274', 0x01050000: 'ITU-R BT.1361', 0x01060000: 'Scene Linear',
    0x01080000: 'Rec.709 xvYCC', 0x010b0000: 'ITU-R BT.2100 HLG',
    0x01010101: 'DVW-709 Like', 0x01010102: 'E10/E30STD for J EK',
    0x01010103: 'E10/E30STD for UC', 0x01010106: 'BBC Initial50',
    0x01010107: 'SD CamCorder STD', 0x01010108: 'BVW-400 Like', 0x01010109: 'Ikegami',
    0x0101017f: 'Unknown (reproduced)',
    0x01010201: 'HG3250G36', 0x01010202: 'HG4600G30', 0x01010203: 'HG3259G40',
    0x01010204: 'HG4609G33', 0x01010205: 'HG8000G36', 0x01010206: 'HG8000G30',
    0x01010207: 'HG8009G40', 0x01010208: 'HG8009G33',
    0x01010301: 'Cine1', 0x01010302: 'Cine2', 0x01010303: 'Cine3', 0x01010304: 'Cine4',
    0x01010305: 'Kodak 5248 film like', 0x01010306: 'Kodak 5245 film like',
    0x01010307: 'Kodak 5293 film like', 0x01010308: 'Kodak 5296 film like',
    0x01010309: 'Average of Film of MSW-900',
    0x01010501: 'S-Log', 0x01010502: 'FS-Log', 0x01010503: 'R709 180%',
    0x01010504: 'R709 800%', 0x01010506: 'Cine-Log', 0x01010507: 'ASC-CDL',
    0x01010508: 'S-Log2', 0x01010509: 'ACESproxy',
    0x01010601: 'Standard', 0x01010602: 'Still', 0x01010603: 'xvYCC',
    0x01010604: 'S-Gamut3/S-Log3', 0x01010605: 'S-Gamut3.Cine/S-Log3',
    0x01010606: 'ITU-R BT.2020', 0x01010607: 'SMPTE ST 2084 (PQ)',
    0x01010608: 'ITU-R BT.2100 HLG',
    0x01010701: 'Cinematone 1', 0x01010702: 'Cinematone 2',
    0x01010704: 'HLG Live (S-Log3 OOTF)', 0x01010705: 'S-Cinetone',
    0x01010706: 'ACEScct', 0x01010707: 'HLG Mild (S-Log3 OOTF)',
}
for _i in range(1, 10):
    GAMMA[0x01010400 + _i] = 'User curve %d' % _i

SMPTE_PRIMARIES = ['Unknown', 'BT.601 NTSC', 'BT.601 PAL', 'Rec.709', 'Rec.2020',
                   'XYZ', 'Display P3', 'ACES', 'XYZ']
SONY_PRIMARIES = {0x01030101: 'S-Gamut', 0x01030102: 'S-Gamut',
                  0x01030103: 'S-Gamut', 0x01030104: 'S-Gamut3',
                  0x01030105: 'S-Gamut3.Cine'}
CODING_EQ = ['Unknown', 'Rec.601', 'Rec.709', 'SMPTE 240M', 'YCgCo', 'Identity', 'Rec.2020']

AE_MODE = {0x01010000: 'Manual Exposure', 0x01020000: 'Full Auto',
           0x01030000: 'Gain Priority Auto', 0x01040000: 'Iris Priority Auto',
           0x01050000: 'Shutter Priority Auto'}
AF_AREA = {0: 'Manual Focus', 1: 'Center Sensitive Auto Focus', 2: 'Full Screen Sensing Auto Focus',
           3: 'Multi Spot Sensing Auto Focus', 4: 'Single Spot Sensing Auto Focus'}
AWB_MODE = {0: 'Preset White Balance Setup', 1: 'Automatic White Balance',
            2: 'Hold', 3: 'One Push'}
# 0xe303 'Lighting preset': 6 = 'Other' confirmed against Catalyst (a6300, FX30);
# the other names come from ExifTool and are unverified.
LIGHTING_PRESET = {1: 'Incandescent', 2: 'Fluorescent', 4: 'Daylight', 5: 'Cloudy',
                   6: 'Other', 255: 'Preset'}
READOUT = {0: 'Interlaced Field', 1: 'Interlaced Frame', 2: 'Progressive Frame', 255: 'Undefined'}
CC_FILTER = {0: 'Cross effect', 1: 'CC 3200K', 2: 'CC 4300K', 3: 'CC 6300K', 4: 'CC 5600K'}
# 0x8120: only value 2 confirmed against Catalyst (FX6, FX30).
LUMA_RANGE = {2: 'Full Scaled Code'}
ORIENTATION = {0: 'normal'}


# --- primitive decoders ----------------------------------------------------

def _u(d):
    return int.from_bytes(d, 'big') if d else None


def _s(d):
    return int.from_bytes(d, 'big', signed=True) if d else None


def _str(d):
    return d.split(b'\0')[0].decode('utf-8', 'replace').strip()


def _fstop(d):
    return 2 ** (8 * (1 - _u(d) / 65536.0))


def _dist(d):
    """RDD-18 16-bit distance: 4-bit signed base-10 exponent + 12-bit mantissa (metres)."""
    v = _u(d)
    e = (v >> 12) & 0xF
    if e >= 8:
        e -= 16
    return (v & 0x0FFF) * (10.0 ** e)


def _rational(d):
    return struct.unpack('>ii', d[:8])


def _ul_tail(d):
    return struct.unpack('>I', d[12:16])[0] if len(d) >= 16 else None


def _gamma(d):
    return GAMMA.get(_ul_tail(d), 'UL ' + d.hex())


def _primaries(d):
    if d[8:12] == b'\x0e\x06\x04\x01':
        return SONY_PRIMARIES.get(_ul_tail(d), 'Sony UL ' + d.hex())
    t = (_ul_tail(d) >> 16) & 0xFF
    return SMPTE_PRIMARIES[t] if 0 < t < len(SMPTE_PRIMARIES) else 'UL ' + d.hex()


def _coding(d):
    t = (_ul_tail(d) >> 16) & 0xFF
    return CODING_EQ[t] if 0 < t < len(CODING_EQ) else 'UL ' + d.hex()


def _bcd_datetime(d):
    """d[0] = UTC offset: bits 0-4 in 30-minute steps, bit 5 = negative, bit 6 = DST
    (e.g. 0x02 = +01:00, 0x44 = +02:00, 0x2a = -05:00); then YYYYMMDDhhmmss in BCD."""
    b = d[1:8].hex()
    tz = d[0]
    mins = (tz & 0x1F) * 30
    sign = '-' if tz & 0x20 else '+'
    return '%s-%s-%sT%s:%s:%s%s%02d:%02d' % (b[0:4], b[4:6], b[6:8], b[8:10], b[10:12], b[12:14],
                                             sign, mins // 60, mins % 60)


def _array_count(d):
    if len(d) < 8:
        return None
    n = struct.unpack('>i', d[:4])[0]
    return max(n, 0)


def _pair(fmt):
    return lambda d: struct.unpack(fmt, d[:struct.calcsize(fmt)])


def _gps_coord(d):
    vals = [struct.unpack('>II', d[i:i + 8]) for i in range(0, 24, 8)]
    deg = [n / m if m else 0 for n, m in vals]
    return deg[0] + deg[1] / 60 + deg[2] / 3600


def _enum(table):
    return lambda d: table.get(_u(d), _u(d))


# --- display formatters (Catalyst style) ------------------------------------

def f_num(fmt, unit=''):
    return lambda v: (fmt % v) + unit


def f_frac(v):
    n, m = v
    return '%d/%d sec' % (n, m) if n == 1 else '%.4g sec' % (n / m)


def f_fps(v):
    n, m = v
    r = n / m if m else 0
    return ('%gp' % r) if abs(r - round(r)) < 1e-6 else '%.2fp' % r


def f_ratio(sep):
    return lambda v: '%d%s%d' % (v[0], sep, v[1])


F_STR = str

# tag -> (key, Catalyst label, decoder, formatter)
TAGS = {
    # Lens unit (RDD 18)
    0x8000: ('iris_fnumber', 'Iris f-number', _fstop, f_num('%.2f')),
    0x8001: ('focus_distance_m', 'Focus position from image plane', _dist, f_num('%.3f', ' m')),
    0x8002: ('focus_distance_front_m', 'Focus position from front lens vertex', _dist, f_num('%.3f', ' m')),
    0x8003: ('macro', 'Macro setting', lambda d: bool(_u(d)), F_STR),
    0x8004: ('focal_length_35mm', 'Lens zoom 35mm still-camera equivalent',
             lambda d: _dist(d) * 1000, f_num('%.3g', ' mm')),
    0x8005: ('focal_length_mm', 'Lens zoom actual focal length',
             lambda d: _dist(d) * 1000, f_num('%.3g', ' mm')),
    0x8006: ('optical_extender_pct', 'Optical extender magnification', _u, f_num('%d', ' %')),
    0x8007: ('lens_attributes', 'Lens attributes', _str, F_STR),
    0x8008: ('iris_tnumber', 'Iris T-number', _fstop, f_num('%.2f')),
    0x8009: ('iris_ring', 'Iris ring position', _u, F_STR),
    0x800a: ('focus_ring', 'Focus ring position', _u, F_STR),
    0x800b: ('zoom_ring', 'Zoom ring position', _u, F_STR),
    # Camera unit (RDD 18)
    0x3210: ('capture_gamma', 'Capture gamma equation', _gamma, F_STR),
    0x3219: ('color_primaries', 'Color primaries', _primaries, F_STR),
    0x321a: ('coding_equations', 'Coding equations', _coding, F_STR),
    0x8100: ('ae_mode', 'Auto exposure mode', lambda d: AE_MODE.get(_ul_tail(d), 'UL ' + d.hex()), F_STR),
    0x8101: ('af_area', 'Auto focus sensing area setting', _enum(AF_AREA), F_STR),
    0x8102: ('cc_filter', 'Color correction filter wheel', _enum(CC_FILTER), F_STR),
    0x8103: ('nd_filter', 'ND filter wheel', lambda d: 'Clear' if _u(d) == 1 else '1/%d' % _u(d), F_STR),
    0x8104: ('sensor_width_um', 'Image sensor effective width', _u, f_num('%d', ' um')),
    0x8105: ('sensor_height_um', 'Image sensor effective height', _u, f_num('%d', ' um')),
    0x8106: ('capture_fps', 'Capture frame rate', _rational, f_fps),
    0x8107: ('readout_mode', 'Image sensor readout mode', _enum(READOUT), F_STR),
    0x8108: ('shutter_angle', 'Shutter angle', lambda d: _s(d) / 60.0, f_num('%.2f', ' deg')),
    0x8109: ('shutter_speed', 'Shutter speed', _rational, f_frac),
    0x810a: ('master_gain_db', 'Camera master gain adjustment', lambda d: _s(d) / 100.0, f_num('%.2f', ' dB')),
    0x810b: ('iso', 'ISO sensitivity', _u, F_STR),
    0x810c: ('electrical_extender_pct', 'Electrical extender magnification', _u, f_num('%d', ' %')),
    0x810d: ('awb_mode', 'Auto white balance mode', _enum(AWB_MODE), F_STR),
    0x810e: ('white_balance_k', 'White balance', _u, f_num('%d', ' K')),
    0x810f: ('master_black_level', 'Camera master black level', lambda d: _u(d) / 10.0, f_num('%.1f', ' %')),
    0x8110: ('knee_point', 'Camera knee point', lambda d: _u(d) / 10.0, f_num('%.1f', ' %')),
    0x8111: ('knee_slope', 'Camera knee slope', _rational, lambda v: '%g' % (v[0] / v[1] if v[1] else 0)),
    0x8112: ('luminance_dynamic_range', 'Camera luminance dynamic range', lambda d: _u(d) / 10.0, f_num('%.1f', ' %')),
    0x8113: ('setting_file_uri', 'Camera setting file URI', _str, F_STR),
    0x8114: ('camera_attributes', 'Camera attributes', _str, F_STR),
    0x8115: ('exposure_index', 'Exposure index', _u, F_STR),
    0x8116: ('gamma_for_cdl', 'Gamma for CDL', _u, F_STR),
    0x8119: ('exposure_index_2', 'Exposure index (32-bit)', _u, F_STR),
    0x811e: ('iso_2', 'ISO sensitivity (32-bit)', _u, F_STR),
    # Sony records the tint as a signed integer in HUNDREDTHS of a tint unit: an FX6
    # clip that Catalyst Browse and Resolve's Camera Raw both read as 15.17 carries
    # 1517 here. Handing the raw integer to a white-balance model turns a routine
    # green/magenta trim into a white point far outside the spectral locus, whose von
    # Kries ratios come out negative - measured on FX6_0024.MXF: R -0.95, G +1.17,
    # B -1.73, i.e. a picture with only its green channel left, and no setting of the
    # Tint slider able to undo it. Scaled here, once, so the number this decoder
    # reports is the one the camera menu, Catalyst and Resolve all show.
    0x811f: ('tint', 'Tint Correction', lambda d: _s(d) / 100.0 if _s(d) is not None else None,
             f_num('%g')),
    0x8120: ('luminance_code_range', 'Luminance code range', _enum(LUMA_RANGE), F_STR),
    # GPS
    0x8500: ('gps_version', 'GPS version', lambda d: '.'.join(str(b) for b in d[:4]), F_STR),
    0x8501: ('gps_lat_ref', 'GPS latitude ref', _str, F_STR),
    0x8502: ('gps_lat', 'GPS latitude', _gps_coord, f_num('%.6f')),
    0x8503: ('gps_lon_ref', 'GPS longitude ref', _str, F_STR),
    0x8504: ('gps_lon', 'GPS longitude', _gps_coord, f_num('%.6f')),
    0x8505: ('gps_alt_ref', 'GPS altitude ref', _u, F_STR),
    0x8506: ('gps_alt', 'GPS altitude', lambda d: (lambda r: r[0] / r[1] if r[1] else None)(_rational(d)), f_num('%.1f', ' m')),
    0x8509: ('gps_status', 'GPS status', _str, F_STR),
    0x8512: ('gps_map_datum', 'GPS map datum', _str, F_STR),
    0x851d: ('gps_date', 'GPS date', _str, F_STR),
    # User-defined acquisition metadata (Sony)
    0xe000: ('udam_set_id', 'UDAM set identifier', lambda d: d.hex(), F_STR),
    0xe101: ('marker_coverage', 'Effective marker coverage', _pair('>II'), f_ratio('/')),
    0xe102: ('marker_aspect', 'Effective marker aspect ratio', _pair('>II'), f_ratio(':')),
    0xe103: ('camera_process_code', 'Camera process discrimination code', lambda d: d.hex(), F_STR),
    0xe104: ('rotary_shutter', 'Rotary shutter mode', lambda d: bool(_u(d)), F_STR),
    0xe108: ('monitoring_characteristics', 'Monitoring characteristics', _gamma, F_STR),
    0xe109: ('monitoring_descriptions', 'Monitoring descriptions', _str, F_STR),
    0xe10a: ('image_orientation', 'Image orientation', _enum(ORIENTATION), F_STR),
    0xe10b: ('monitoring_base_curve', 'Monitoring base curve', _gamma, F_STR),
    0xe10d: ('monitoring_primaries', 'Monitoring color primaries', _primaries, F_STR),
    0xe10e: ('monitoring_coding', 'Monitoring coding equations', _coding, F_STR),
    0xe10f: ('active_area_aspect', 'Active area aspect ratio', _pair('>II'), f_ratio(':')),
    0xe110: ('pixel_aspect', 'Pixel aspect ratio', _pair('>BB'), f_ratio(':')),
    0xe111: ('look_gamma', 'Gamma for look', _gamma, F_STR),
    0xe112: ('look_color', 'Color for look', _primaries, F_STR),
    0xe113: ('pre_cdl_transform', 'Pre-CDL transform', _str, F_STR),
    0xe114: ('post_cdl_transform', 'Post-CDL transform', _str, F_STR),
    0xe115: ('look_baked', 'Look process baked', lambda d: bool(_u(d)), lambda v: str(v).lower()),
    0xe300: ('image_stabilizer', 'Image stabilizer', lambda d: 'enabled' if _u(d) == 0 else 'disabled', F_STR),
    0xe301: ('iso_3', 'ISO sensitivity (Sony)', _u, F_STR),
    0xe302: ('gain_setting_type', 'Gain setting type', lambda d: 'ISO' if _u(d) else 'dB', F_STR),
    0xe303: ('lighting_preset', 'Lighting preset', _enum(LIGHTING_PRESET), F_STR),
    0xe304: ('recording_time', 'Recording time', _bcd_datetime, F_STR),
    # Imager / IBIS / lens OSS / IMU (summarised; used by stabilisation tools)
    0xe405: ('sensor_pixels', 'Sensor size (px)', _pair('>HH'), f_ratio(' x ')),
    0xe407: ('pixel_pitch_nm', 'Pixel pitch (nm)', _pair('>HH'), f_ratio(' x ')),
    0xe409: ('capture_area_origin', 'Capture area origin', _pair('>II'), f_ratio(', ')),
    0xe40a: ('capture_area_size', 'Capture area size', _pair('>II'), f_ratio(' x ')),
    0xe40c: ('first_frame_ts_ms', 'First frame timestamp', lambda d: _s(d) / 1000.0, f_num('%.3f', ' ms')),
    0xe40d: ('exposure_time_ms', 'Exposure time', lambda d: _s(d) / 1000.0, f_num('%.3f', ' ms')),
    0xe40e: ('frame_readout_ms', 'Frame readout time (rolling shutter)', lambda d: _s(d) / 1000.0, f_num('%.3f', ' ms')),
    0xe40f: ('ibis_samples', 'IBIS samples / frame', _array_count, F_STR),
    0xe450: ('ibis_samples_2', 'IBIS samples #2 / frame', _array_count, F_STR),
    0xe410: ('lens_position_nm', 'Lens position (nm)', _pair('>iii'), lambda v: '%d, %d, %d' % v),
    0xe416: ('lens_oss_samples', 'Lens OSS samples / frame', _array_count, F_STR),
    0xe420: ('lens_distortion_data', 'Lens distortion data', lambda d: bool(_u(d)), F_STR),
    0xe422: ('focal_plane_distortion_data', 'Focal plane distortion data', lambda d: bool(_u(d)), F_STR),
    0xe424: ('mesh_correction', 'Mesh correction', lambda d: bool(_u(d)), F_STR),
    0xe435: ('gyro_hz', 'Gyroscope frequency', _s, f_num('%d', ' Hz')),
    0xe43b: ('gyro_samples', 'Gyroscope samples / frame', _array_count, F_STR),
    0xe445: ('accel_hz', 'Accelerometer frequency', _s, f_num('%d', ' Hz')),
    0xe44b: ('accel_samples', 'Accelerometer samples / frame', _array_count, F_STR),
    0xe502: ('lens_id', 'Lens ID', _u, F_STR),
    0xe521: ('lens_focal_length_breathing', 'Focal length (breathing data)', lambda d: _s(d) / 10.0, f_num('%.1f', ' mm')),
    0xe530: ('breathing_comp_enabled', 'Breathing compensation enabled', lambda d: _u(d) != 0, F_STR),
    0xe531: ('breathing_comp_applied', 'Breathing compensation applied', lambda d: _u(d) != 0, F_STR),
}


def _hex(d):
    return d.hex() if len(d) <= 48 else d[:48].hex() + '…(%d B)' % len(d)


def _f32(d):
    return struct.unpack('>f', d[:4])[0]


def _ms(d):
    return _s(d) / 1000.0


# Stabilisation / lens-model internals (labels from telemetry-parser). Values are
# shown as-is: they matter to Gyroflow / Catalyst Stabilize, not to grading.
for _tag, _key, _label, _fn, _fmt in (
        (0xe408, 'capture_area_unit', 'Capture area unit (1/x px)', _s, F_STR),
        (0xe421, 'lens_distortion_table', 'Lens distortion table', _hex, F_STR),
        (0xe423, 'focal_plane_distortion_table', 'Focal plane distortion table', _hex, F_STR),
        (0xe425, 'mesh_base_fov_height', 'Mesh base FOV reference height', _s, F_STR),
        (0xe42f, 'mesh_correction_data', 'Mesh correction data', _hex, F_STR),
        (0xe437, 'gyro_time_offset_ms', 'Gyroscope time offset', _ms, f_num('%.3f', ' ms')),
        (0xe439, 'gyro_scale', 'Gyroscope scale', _f32, f_num('%g')),
        (0xe43a, 'gyro_orientation', 'Gyroscope orientation', _hex, F_STR),
        (0xe43d, 'gyro_zero_offset', 'Gyroscope zero-rate offset', _pair('>hhh'), lambda v: '%d, %d, %d' % v),
        (0xe43e, 'gyro_offset_info', 'Gyroscope offset info', _hex, F_STR),
        (0xe447, 'accel_time_offset_ms', 'Accelerometer time offset', _ms, f_num('%.3f', ' ms')),
        (0xe449, 'accel_scale', 'Accelerometer scale', _f32, f_num('%g')),
        (0xe44a, 'accel_orientation', 'Accelerometer orientation', _hex, F_STR),
        (0xe501, 'lens_frame_period_ms', 'Lens data frame period', _ms, f_num('%.3f', ' ms')),
        (0xe503, 'lens_system_flags_1', 'Camera system flags 1', _hex, F_STR),
        (0xe504, 'lens_system_flags_2', 'Camera system flags 2', _hex, F_STR),
        (0xe511, 'lens_frame_counter', 'Lens data frame counter / phase', _hex, F_STR),
        (0xe512, 'lens_samples_before', 'Focus/zoom samples before frame', _u, F_STR),
        (0xe513, 'lens_samples_after', 'Focus/zoom samples after frame', _u, F_STR),
        (0xe514, 'lens_phase_den', 'Sample phase denominator', _u, F_STR),
        (0xe515, 'lens_phase_mode', 'Sample phase mode', _u, F_STR),
        (0xe516, 'lens_exposure_time_ms', 'Exposure time (lens data)', _ms, f_num('%.3f', ' ms')),
        (0xe517, 'lens_exposure_offset_ms', 'Exposure offset (lens data)', _ms, f_num('%.3f', ' ms')),
        (0xe518, 'lens_readout_ms', 'Frame readout time (lens data)', _ms, f_num('%.3f', ' ms')),
        (0xe519, 'lens_sensor_px', 'Sensor size (lens data, px)', _pair('>HH'), f_ratio(' x ')),
        (0xe51a, 'lens_capture_origin_px', 'Capture area origin (lens data, px)', _pair('>HH'), f_ratio(', ')),
        (0xe51b, 'lens_capture_size_px', 'Capture area size (lens data, px)', _pair('>HH'), f_ratio(' x ')),
        (0xe51c, 'lens_pixel_pitch_nm', 'Pixel pitch (lens data, nm)', _pair('>HH'), f_ratio(' x ')),
        (0xe523, 'zoom_position_samples', 'Zoom position samples', _hex, F_STR),
        (0xe524, 'focus_position_samples', 'Focus position samples', _hex, F_STR),
        (0xe525, 'focus_position_samples_late', 'Focus position samples (delayed)', _hex, F_STR),
        (0xe526, 'focus_samples_delay', 'Delayed focus samples offset (frames)', _u, F_STR),
        (0xe527, 'zoom_samples_hr', 'High-rate zoom position samples', _hex, F_STR),
        (0xe528, 'focus_samples_hr', 'High-rate focus position samples', _hex, F_STR),
        (0xe52a, 'lens_restart_counter', 'Restart activation counter', _hex, F_STR),
        (0xe532, 'magnification_no_stab', 'Magnification scale (no stabilization)', _hex, F_STR),
        (0xe533, 'magnification_stab', 'Magnification scale (stabilization)', _hex, F_STR),
        (0xe534, 'breathing_mag_min', 'Minimum breathing magnification', _hex, F_STR),
        (0xe535, 'breathing_mag_max', 'Maximum breathing magnification', _hex, F_STR),
        (0xe536, 'breathing_mag_frame', 'Breathing magnification of the frame', _hex, F_STR),
        (0xe537, 'breathing_mag_applied', 'Magnification applied in-camera', _hex, F_STR),
        (0xe538, 'breathing_mag_applied_2', 'Magnification applied in-camera (copy)', _hex, F_STR),
        (0xe539, 'breathing_mag_reference', 'Reference magnification ratio', _hex, F_STR)):
    TAGS[_tag] = (_key, _label, _fn, _fmt)


def display_value(key, value):
    """Format a decoded value with the Catalyst-style formatter of its tag."""
    for spec in TAGS.values():
        if spec[0] == key:
            try:
                return spec[3](value)
            except Exception:
                break
    return str(value)


def iter_packs(buf, pos=0):
    """Yield (set_ul_tail_hex, value_bytes) for each KLV pack starting at pos."""
    while pos + 17 <= len(buf):
        key = buf[pos:pos + 16]
        if key[:4] != UL_PREFIX:
            return
        l = buf[pos + 16]
        if l & 0x80:
            n = l & 0x7F
            length = int.from_bytes(buf[pos + 17:pos + 17 + n], 'big')
            vs = pos + 17 + n
        else:
            length, vs = l, pos + 17
        yield key[8:16].hex(), buf[vs:vs + length]
        pos = vs + length


def iter_local_tags(body):
    q = 0
    while q + 4 <= len(body):
        tag, ln = struct.unpack('>HH', body[q:q + 4])
        if q + 4 + ln > len(body):
            return  # truncated read
        yield tag, body[q + 4:q + 4 + ln]
        q += 4 + ln


def decode(buf, pos=0):
    """Decode rtmd packs starting at byte offset pos.

    MP4 samples start with a header whose first u16 is its length (use
    decode_mp4_sample); MXF ANC payloads start directly with the first pack.
    Returns a list of entries {tag, set, key, label, value, display, raw}.
    """
    out = []
    for set_ul, body in iter_packs(buf, pos):
        set_name = SET_NAMES.get(set_ul, set_ul)
        for tag, data in iter_local_tags(body):
            spec = TAGS.get(tag)
            raw = data.hex() if len(data) <= 48 else data[:48].hex() + '…(%d B)' % len(data)
            entry = {'tag': '0x%04x' % tag, 'set': set_name, 'raw': raw}
            if spec:
                key, label, fn, fmt = spec
                try:
                    value = fn(data)
                    display = fmt(value)
                except Exception:  # malformed value: keep raw only
                    value, display = None, raw
                entry.update(key=key, label=label, value=value, display=display)
            else:
                entry.update(key=None, label='Unknown 0x%04x' % tag, value=None, display=raw)
            out.append(entry)
    return out


def decode_mp4_sample(buf):
    if len(buf) < 2:
        return []
    return decode(buf, struct.unpack('>H', buf[:2])[0])


def values(entries):
    """Flatten decoded entries into {key: value} (first occurrence wins)."""
    v = {}
    for e in entries:
        if e['key'] and e['value'] is not None and e['key'] not in v:
            v[e['key']] = e['value']
    return v
