# SPDX-License-Identifier: GPL-3.0-or-later
"""S-Log MetaRaw launcher for DaVinci Resolve: Workspace > Scripts.

Installed by install.sh into Fusion/Scripts/Utility; LIB_DIR is replaced at
install time with the folder that contains the 'slogmetaraw' package.
Startup failures are reported in a dialog and in ~/Library/Logs/SLogMetaRaw.
"""
import os
import socket
import subprocess
import sys
import time
import traceback

LIB_DIR = '/Library/Application Support/SLogMetaRaw/lib'
LOG_PATH = os.path.expanduser('~/Library/Logs/SLogMetaRaw/launcher.log')
PROJECT_WAIT = 3.0   # seconds for Fusion and the open project once Resolve answers


def _log(message):
    """Diagnostics must never prevent the script from opening."""
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, 'a', encoding='utf-8') as stream:
            stream.write('%s %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), message))
    except OSError:
        pass


def _report_error(message, detail):
    _log(detail)
    try:
        print('S-Log MetaRaw: %s\n%s' % (message, detail), file=sys.stderr)
    except (OSError, AttributeError):
        pass
    # Passing the message as argv preserves accents and quotes without generating
    # AppleScript source from exception text or a user's installation path.
    script = ('on run argv\n'
              'display dialog (item 1 of argv) with title "S-Log MetaRaw" '
              'buttons {"OK"} default button "OK" with icon caution\n'
              'end run')
    try:
        subprocess.run(['/usr/bin/osascript', '-e', script,
                        message[:700] + '\n\nDettagli: ' + LOG_PATH],
                       timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        pass


def _retry(obtain, message, attempts=40, interval=0.25):
    """Allow Resolve to finish connecting/loading, retaining the last failure."""
    last_error = None
    deadline = time.monotonic() + attempts * interval
    for attempt in range(attempts):
        try:
            value = obtain()
            if value is not None and value is not False:
                return value
        except Exception as exc:
            last_error = exc
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        if attempt + 1 < attempts:
            time.sleep(min(interval, remaining))
    raise RuntimeError(message) from last_error


def _local_ipv4_addresses():
    """Assigned addresses on this Mac only; never discover other Resolve hosts.

    Resolve can register scripting on the Mac's interface address while refusing
    127.0.0.1. Read the local interface inventory instead of using pinghosts(),
    which can discover Resolve instances belonging to other computers.
    """
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


def _connect(namespace, bmd):
    """Prefer the menu's existing connection before opening another API session.

    Depending on Resolve's launch context, Fusion is injected as fusion, fu or
    app. Its GetResolve() can supply the connection even when scriptapp('Resolve')
    is unavailable. A failure in one route must not skip the remaining routes.
    """
    routes = [('resolve globale', lambda: namespace.get('resolve'))]
    for name in ('fusion', 'fu', 'app'):
        obj = namespace.get(name)
        if obj is not None:
            routes.append((name + '.GetResolve()', lambda obj=obj: obj.GetResolve()))
    routes.extend([
        ("scriptapp('Resolve')", lambda: bmd.scriptapp('Resolve')),
        ("scriptapp('Fusion').GetResolve()", lambda: bmd.scriptapp('Fusion').GetResolve()),
    ])
    last_error = None
    for label, obtain in routes:
        try:
            resolve = obtain()
            if resolve is not None and resolve is not False:
                _log('Connessione: ' + label)
                return resolve
        except Exception as exc:
            last_error = exc
    for address in _local_ipv4_addresses():
        try:
            resolve = bmd.scriptapp('Resolve', address, 1.0)
            if resolve is not None and resolve is not False:
                _log('Connessione: indirizzo locale ' + address)
                return resolve
        except Exception as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    return None


def _fusion(namespace, resolve):
    for name in ('fusion', 'fu', 'app'):
        candidate = namespace.get(name)
        if candidate is not None and getattr(candidate, 'UIManager', None) is not None:
            return candidate
    return resolve.Fusion()


def _load_ui():
    if not os.path.isfile(os.path.join(LIB_DIR, 'slogmetaraw', '__init__.py')):
        raise RuntimeError('La libreria S-Log MetaRaw non si trova in:\n%s\n'
                           'Reinstalla lo script dalla cartella del programma.' % LIB_DIR)
    if LIB_DIR in sys.path:
        sys.path.remove(LIB_DIR)
    sys.path.insert(0, LIB_DIR)
    for name in list(sys.modules):
        if name == 'slogmetaraw' or name.startswith('slogmetaraw.'):
            del sys.modules[name]  # always pick up the installed version
    from slogmetaraw import ui
    return ui


def main(namespace=None):
    namespace = globals() if namespace is None else namespace
    _log('Avvio: Python %s; eseguibile=%s; libreria=%s; globals=%s' % (
        sys.version.split()[0], sys.executable, LIB_DIR,
        ', '.join(name for name in ('bmd', 'resolve', 'fusion', 'fu', 'app')
                  if namespace.get(name) is not None)))
    try:
        bmd = namespace.get('bmd')
        if bmd is None:
            import DaVinciResolveScript as bmd
        resolve = namespace.get('resolve')
        if resolve is not None:
            _log('Connessione: resolve globale')
        else:
            # started outside the menu: Resolve may still be finishing its launch
            resolve = _retry(lambda: _connect(namespace, bmd),
                             'S-Log MetaRaw non riesce a collegarsi a DaVinci Resolve.\n'
                             'Apri un progetto e rilancia da Workspace > Scripts. '
                             'Se il problema persiste, chiudi e riapri Resolve.')
        fusion = _retry(lambda: _fusion(namespace, resolve),
                        'L\'interfaccia Fusion di DaVinci Resolve non è disponibile.',
                        attempts=int(PROJECT_WAIT / 0.25))
        _retry(lambda: resolve.GetProjectManager().GetCurrentProject(),
               'Non c\'è un progetto aperto. Apri un progetto in DaVinci Resolve '
               'e rilancia S-Log MetaRaw da Workspace > Scripts.',
               attempts=int(PROJECT_WAIT / 0.25))
        if getattr(fusion, 'UIManager', None) is None:
            raise RuntimeError('UIManager non è disponibile. La finestra S-Log MetaRaw '
                               'richiede DaVinci Resolve Studio.')
        ui = _load_ui()
        _log('Avvio interfaccia')
        ui.main(resolve, fusion, bmd)
        _log('Interfaccia chiusa')
        return True
    except Exception as exc:
        _report_error(str(exc), traceback.format_exc())
        return False


if globals().get('__name__', '__main__') == '__main__':
    main()
