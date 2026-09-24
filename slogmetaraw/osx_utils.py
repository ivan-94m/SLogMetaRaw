# SPDX-License-Identifier: GPL-3.0-or-later
"""Small macOS helpers for the S-Log MetaRaw window: None / no-op on failure, never required."""
import ctypes
import ctypes.util
import os
import subprocess

_kCGWindowListOptionOnScreenOnly = 1
_kCGWindowListExcludeDesktopElements = 16
_kCFStringEncodingUTF8 = 0x08000100
_kCFNumberDoubleType = 13

SOUND_OK = '/System/Library/Sounds/Glass.aiff'
SOUND_ERR = '/System/Library/Sounds/Basso.aiff'


class _CGPoint(ctypes.Structure):
    _fields_ = [('x', ctypes.c_double), ('y', ctypes.c_double)]


class _CGSize(ctypes.Structure):
    _fields_ = [('width', ctypes.c_double), ('height', ctypes.c_double)]


class _CGRect(ctypes.Structure):
    _fields_ = [('origin', _CGPoint), ('size', _CGSize)]


_cg = None


def _coregraphics():
    global _cg
    if _cg is None:
        path = ctypes.util.find_library('CoreGraphics') or \
            '/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics'
        cg = ctypes.CDLL(path)
        cg.CGMainDisplayID.restype = ctypes.c_uint32
        cg.CGDisplayBounds.argtypes = [ctypes.c_uint32]
        cg.CGDisplayBounds.restype = _CGRect
        cg.CGWindowListCopyWindowInfo.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
        cg.CGWindowListCopyWindowInfo.restype = ctypes.c_void_p
        cg.CFArrayGetCount.argtypes = [ctypes.c_void_p]
        cg.CFArrayGetCount.restype = ctypes.c_long
        cg.CFArrayGetValueAtIndex.argtypes = [ctypes.c_void_p, ctypes.c_long]
        cg.CFArrayGetValueAtIndex.restype = ctypes.c_void_p
        cg.CFDictionaryGetValue.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        cg.CFDictionaryGetValue.restype = ctypes.c_void_p
        cg.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
        cg.CFStringCreateWithCString.restype = ctypes.c_void_p
        cg.CFStringGetCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]
        cg.CFStringGetCString.restype = ctypes.c_bool
        cg.CFNumberGetValue.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        cg.CFNumberGetValue.restype = ctypes.c_bool
        cg.CFRelease.argtypes = [ctypes.c_void_p]
        _cg = cg
    return _cg


def _cfstring(s):
    return _coregraphics().CFStringCreateWithCString(None, s.encode('utf-8'), _kCFStringEncodingUTF8)


def _cfstring_value(ref):
    if not ref:
        return ''
    cg = _coregraphics()
    buf = ctypes.create_string_buffer(512)
    if cg.CFStringGetCString(ref, buf, 512, _kCFStringEncodingUTF8):
        return buf.value.decode('utf-8')
    return ''


def _cfnumber_double(ref):
    if not ref:
        return 0.0
    cg = _coregraphics()
    v = ctypes.c_double()
    if cg.CFNumberGetValue(ref, _kCFNumberDoubleType, ctypes.byref(v)):
        return v.value
    return 0.0


def display_bounds():
    """(x, y, w, h) of the main display, top-left origin, or None."""
    try:
        cg = _coregraphics()
        r = cg.CGDisplayBounds(cg.CGMainDisplayID())
        if r.size.width <= 0 or r.size.height <= 0:
            return None   # no display is accessible (e.g. a headless session)
        return (int(r.origin.x), int(r.origin.y), int(r.size.width), int(r.size.height))
    except Exception:
        return None


def resolve_window_bounds():
    """(x, y, w, h) of the largest on-screen window owned by DaVinci Resolve, or None.

    Uses CGWindowListCopyWindowInfo, which reports window geometry of other apps
    without special permissions (window *titles* would need Screen Recording, so
    we never read them). Falls back to None when Resolve is not running.
    """
    arr = None
    keys = {}
    best = None
    try:
        cg = _coregraphics()
        arr = cg.CGWindowListCopyWindowInfo(
            _kCGWindowListOptionOnScreenOnly | _kCGWindowListExcludeDesktopElements, 0)
        if not arr:
            return None
        for name in ('kCGWindowOwnerName', 'kCGWindowBounds', 'X', 'Y', 'Width', 'Height'):
            keys[name] = _cfstring(name)
            if not keys[name]:
                return None
        count = cg.CFArrayGetCount(arr)
        for i in range(count):
            info = cg.CFArrayGetValueAtIndex(arr, i)
            if not info:
                continue
            owner = cg.CFDictionaryGetValue(info, keys['kCGWindowOwnerName'])
            bounds = cg.CFDictionaryGetValue(info, keys['kCGWindowBounds'])
            if not owner or not bounds:
                continue
            if 'resolve' not in _cfstring_value(owner).lower():
                continue
            x = _cfnumber_double(cg.CFDictionaryGetValue(bounds, keys['X']))
            y = _cfnumber_double(cg.CFDictionaryGetValue(bounds, keys['Y']))
            w = _cfnumber_double(cg.CFDictionaryGetValue(bounds, keys['Width']))
            h = _cfnumber_double(cg.CFDictionaryGetValue(bounds, keys['Height']))
            if w > 200 and h > 200 and (best is None or w * h > best[2] * best[3]):
                best = (int(x), int(y), int(w), int(h))
    except Exception:
        return None
    finally:
        if arr:
            cg.CFRelease(arr)
        for key in keys.values():
            if key:
                cg.CFRelease(key)
    return best


def play_sound(ok=True):
    """Fire-and-forget notification sound (different one on errors). Never raises."""
    path = SOUND_OK if ok else SOUND_ERR
    try:
        if os.path.exists(path):
            subprocess.Popen(['/usr/bin/afplay', path],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(['/usr/bin/osascript', '-e', 'beep'],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
