# SPDX-License-Identifier: GPL-2.0-or-later
"""HID device abstraction layer."""

try:
    import hid
except ImportError:
    import hidraw as hid
