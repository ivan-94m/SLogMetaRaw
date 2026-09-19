# SPDX-License-Identifier: GPL-3.0-or-later
# S-Log MetaRaw - Copyright (C) 2026 Ivan Mazzone
# Free software under the GNU General Public License v3 or later; no warranty.
# See the LICENSE file or https://www.gnu.org/licenses/gpl-3.0.html
"""S-Log MetaRaw: read Sony XAVC (MP4/MXF) acquisition metadata for DaVinci Resolve.

Ivan Mazzone + Claude (@Ivan_94m).
"""
from .extract import read_clip, DatalessError, find_sidecar  # noqa: F401

__version__ = '1.0.1'
