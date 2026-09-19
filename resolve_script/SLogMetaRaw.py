# SPDX-License-Identifier: GPL-3.0-or-later
"""S-Log MetaRaw launcher for DaVinci Resolve: Workspace > Scripts > S-Log MetaRaw.

Installed by install.sh into Fusion/Scripts/Utility; LIB_DIR is replaced at
install time with the folder that contains the 'slogmetaraw' package.
"""
import sys

LIB_DIR = '__LIB_DIR__'
if LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)

for _name in [m for m in sys.modules if m == 'slogmetaraw' or m.startswith('slogmetaraw.')]:
    del sys.modules[_name]  # always pick up the installed version

from slogmetaraw import ui  # noqa: E402

try:
    _bmd = bmd  # noqa: F821  (injected by Resolve)
except NameError:
    import DaVinciResolveScript as _bmd
try:
    _resolve = resolve  # noqa: F821
except NameError:
    _resolve = _bmd.scriptapp('Resolve')
try:
    _fusion = fusion  # noqa: F821
except NameError:
    _fusion = _resolve.Fusion()

ui.main(_resolve, _fusion, _bmd)
