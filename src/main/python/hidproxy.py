# SPDX-License-Identifier: GPL-2.0-or-later
"""HID device abstraction layer."""

import sys

try:
    import hid
except ImportError:
    import hidraw as hid

# Enable non-exclusive mode on macOS to allow multiple HID clients
if sys.platform == "darwin" and hasattr(hid, "darwin_set_open_exclusive"):
    hid.darwin_set_open_exclusive(0)
