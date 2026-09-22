# SPDX-License-Identifier: GPL-3.0-or-later
"""Write a Resolve launcher with its library path encoded as a Python literal."""
import os
from pathlib import Path
import sys
import tempfile


def render_launcher(source, library, destination):
    source = Path(source)
    destination = Path(destination)
    template = source.read_text(encoding='utf-8')
    placeholder = "'__LIB_DIR__'"
    if template.count(placeholder) != 1:
        raise ValueError('The launcher must contain exactly one quoted __LIB_DIR__ placeholder')
    rendered = template.replace(placeholder, repr(str(library)))
    # A bad template must never replace the working menu entry.
    compile(rendered, str(destination), 'exec')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=destination.parent,
                                         prefix='.slogmetaraw-', delete=False) as handle:
            temporary = handle.name
            handle.write(rendered)
        os.chmod(temporary, 0o644)
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None:
            os.unlink(temporary)


if __name__ == '__main__':
    if len(sys.argv) != 4:
        sys.exit('Usage: render_launcher.py SOURCE LIBRARY DESTINATION')
    render_launcher(*sys.argv[1:])
