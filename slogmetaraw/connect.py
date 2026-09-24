# SPDX-License-Identifier: GPL-3.0-or-later
"""Connection to the local DaVinci Resolve scripting server and single-clip write.

Used by ``python -m slogmetaraw --to-resolve <path>``, the child process that the
OpenFX plugin starts when its "Rileggi metadata" button is pressed. The child
runs under ResolvePython (isolated mode), so DaVinciResolveScript is imported
lazily, only when a connection is actually attempted.

Resolve 21.x can refuse scriptapp('Resolve') on 127.0.0.1 while accepting an
address assigned to one of the Mac's interfaces (same behaviour documented in
the launcher), so the fallback tries the local IPv4 addresses read from ifconfig.
"""

import os
import socket
import subprocess
import unicodedata


def _local_ipv4_addresses():
    """Assigned IPv4 addresses on this Mac only; never discover other hosts."""
    try:
        result = subprocess.run(['/sbin/ifconfig', '-a'], capture_output=True,
                                text=True, timeout=2, check=True)
    except (OSError, subprocess.SubprocessError):
        return []
    addresses = []
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) < 2 or fields[0] != 'inet':
            continue
        address = fields[1]
        try:
            socket.inet_pton(socket.AF_INET, address)
        except OSError:
            continue
        if address != '0.0.0.0' and not address.startswith('127.') and address not in addresses:
            addresses.append(address)
    return addresses


def connect():
    """A connected Resolve object, or raise RuntimeError with a user-readable reason.

    The caller never touches DaVinciResolveScript itself: under ResolvePython the
    module lives in the runtime's own lib/modules, under a plain Python it does
    not exist at all."""
    try:
        import DaVinciResolveScript as bmd
    except Exception as exc:
        raise RuntimeError('modulo DaVinciResolveScript non disponibile (%s)' % exc)
    resolve = None
    try:
        resolve = bmd.scriptapp('Resolve')
    except Exception:
        resolve = None
    if resolve:
        return resolve
    for address in _local_ipv4_addresses():
        try:
            resolve = bmd.scriptapp('Resolve', address, 1.0)
        except Exception:
            resolve = None
        if resolve:
            return resolve
    raise RuntimeError('connessione a DaVinci Resolve non riuscita: controlla che '
                       'Resolve sia aperto con un progetto e che lo scripting esterno sia attivo')


def _nfc(path):
    return unicodedata.normalize('NFC', path)


def apply_path(resolve, path, r, set_color_space=False, overwrite=True, add_tags=False,
               set_data_level=True):
    """Write the metadata of one clip into every Media Pool item with that file path.

    Same defaults as the script window (sovrascrivi attivo, tag spenti, input color
    space non toccato). Returns {'written': n, 'failed': n, 'clips': n} or raises
    RuntimeError when the clip is not in the Media Pool."""
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        raise RuntimeError('nessun progetto aperto in Resolve')
    pool = project.GetMediaPool()
    if not pool:
        raise RuntimeError('Media Pool non disponibile')

    from . import resolve_io
    pool_paths = [(clip, resolve_io.clip_path(clip))
                  for clip in resolve_io.iter_media_pool_clips(pool.GetRootFolder())]
    pool_paths = [(clip, _nfc(p)) for clip, p in pool_paths if p]
    wanted = _nfc(path)
    matches = [clip for clip, p in pool_paths if p == wanted]
    if not matches:
        # a symlink on either side: realpath touches the disk, so only when nothing matched
        real = _nfc(os.path.realpath(path))
        matches = [clip for clip, p in pool_paths if _nfc(os.path.realpath(p)) == real]
    written = failed = clips = 0
    level = {}
    for clip in matches:
        report = resolve_io.apply_to_clip(clip, r, set_color_space=set_color_space,
                                          overwrite=overwrite, add_tags=add_tags,
                                          set_data_level=set_data_level)
        written += len(report.get('written') or [])
        failed += len(report.get('failed') or [])
        level = report.get('data_level') or level
        clips += 1
    if clips == 0:
        raise RuntimeError('clip non trovata nel Media Pool: importa la clip e riprova')
    return {'written': written, 'failed': failed, 'clips': clips, 'data_level': level}
