# SPDX-License-Identifier: GPL-2.0-or-later
"""
Device discovery and management for layer monitor.
"""

import time
import logging
import sys

from hidproxy import hid
from protocol.keyboard import Keyboard

# Serial number magic string for Viable device detection
VIABLE_SERIAL_NUMBER_MAGIC = "viable:"

# VIA3 minimum protocol version
VIA3_MIN_PROTOCOL = 12

MSG_LEN = 32


def find_viable_devices(quiet=False):
    """Find all connected Viable keyboards."""
    devices = []
    seen_paths = set()

    for dev in hid.enumerate():
        if dev["path"] in seen_paths:
            continue

        # Check for Viable (0xFF61/0x62) or VIA (0xFF60/0x61) usage page
        is_viable = dev["usage_page"] == 0xFF61 and dev["usage"] == 0x62
        is_via = dev["usage_page"] == 0xFF60 and dev["usage"] == 0x61

        if not (is_viable or is_via):
            continue

        # Check for Viable serial number magic
        if VIABLE_SERIAL_NUMBER_MAGIC not in dev.get("serial_number", ""):
            continue

        if not quiet:
            logging.info("Found device: VID=%04X PID=%04X serial=%s path=%s",
                        dev["vendor_id"], dev["product_id"],
                        dev["serial_number"], dev["path"])

        devices.append(dev)
        seen_paths.add(dev["path"])

    return devices


class KeyboardDevice:
    """Wrapper for a connected keyboard device."""

    def __init__(self, desc):
        self.desc = desc
        self.dev = None
        self.keyboard = None

    def open(self):
        """Open the HID device and initialize keyboard protocol."""
        self.dev = hid.device()
        for x in range(10):
            try:
                self.dev.open_path(self.desc["path"])
                break
            except OSError:
                time.sleep(1)
        else:
            raise RuntimeError("Unable to open device")

        self.keyboard = Keyboard(self.dev)
        self.keyboard.reload()

    def close(self):
        """Close the HID device."""
        if self.dev:
            self.dev.close()
            self.dev = None
            self.keyboard = None

    def get_current_layer(self):
        """Get the current active layer."""
        if self.keyboard:
            return self.keyboard.get_current_layer()
        return None

    def get_layer_colors(self):
        """Get layer colors if available."""
        if self.keyboard and self.keyboard.sval_layer_colors:
            return self.keyboard.sval_layer_colors
        return None

    def title(self):
        """Get a display title for the device."""
        return "{} {}".format(
            self.desc.get("manufacturer_string", ""),
            self.desc.get("product_string", "")
        ).strip()
