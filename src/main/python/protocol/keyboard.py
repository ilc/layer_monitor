# SPDX-License-Identifier: GPL-2.0-or-later
"""
Simplified keyboard protocol for layer monitor.

Only implements what's needed to query the current layer.
"""

import struct
import json
import lzma
import logging

from protocol.client_wrapper import ClientWrapper
from protocol.constants import (
    CMD_VIA_GET_PROTOCOL_VERSION,
    CMD_VIA_CUSTOM_GET_VALUE,
    VIABLE_PREFIX,
    VIABLE_GET_PROTOCOL_INFO,
    VIABLE_DEFINITION_SIZE,
    VIABLE_DEFINITION_CHUNK,
    VIABLE_DEFINITION_CHUNK_SIZE,
)

# VIA custom value IDs for Svalboard
SVAL_ID_LAYER0_COLOR = 32
SVAL_ID_CURRENT_LAYER = 48


class Keyboard:
    """Simplified keyboard class for layer monitoring."""

    def __init__(self, dev):
        self.dev = dev
        self.wrapper = ClientWrapper(dev)
        self.definition = None
        self.is_svalboard = False
        self.sval_layer_colors = None
        self.layers = 0
        self.viable_protocol = None

    def reload(self):
        """Load keyboard information."""
        self._reload_via_protocol()
        self._reload_definition()
        self._reload_layers()
        self._reload_svalboard()

    def _reload_via_protocol(self):
        """Get VIA protocol version."""
        data = self.wrapper.send_via(struct.pack("B", CMD_VIA_GET_PROTOCOL_VERSION), retries=20)
        self.via_protocol = struct.unpack(">H", data[1:3])[0]
        logging.debug("VIA protocol version: %d", self.via_protocol)

    def _reload_definition(self):
        """Load keyboard definition to detect Svalboard."""
        # Probe for Viable protocol
        data = self.wrapper.send_viable(struct.pack("B", VIABLE_GET_PROTOCOL_INFO), retries=5)

        if data[0] != VIABLE_PREFIX or data[1] != VIABLE_GET_PROTOCOL_INFO:
            logging.info("Keyboard does not support Viable protocol")
            self.viable_protocol = None
            return

        version = struct.unpack("<I", bytes(data[2:6]))[0]
        logging.debug("Viable protocol version: %d", version)
        self.viable_protocol = version

        # Get definition size
        data = self.wrapper.send_viable(struct.pack("B", VIABLE_DEFINITION_SIZE), retries=20)
        sz = struct.unpack("<I", bytes(data[2:6]))[0]
        logging.debug("Definition size: %d bytes", sz)

        # Fetch definition chunks
        payload = b""
        offset = 0
        while offset < sz:
            data = self.wrapper.send_viable(
                struct.pack("<BHB", VIABLE_DEFINITION_CHUNK, offset, VIABLE_DEFINITION_CHUNK_SIZE),
                retries=20)
            actual_size = data[4]
            chunk = data[5:5 + actual_size]
            payload += chunk
            offset += actual_size

        self.definition = json.loads(lzma.decompress(payload))

    def _reload_layers(self):
        """Get layer count."""
        data = self.wrapper.send_via(struct.pack("B", 0x11), retries=20)  # CMD_VIA_GET_LAYER_COUNT
        self.layers = data[1]
        logging.debug("Layer count: %d", self.layers)

    def _reload_svalboard(self):
        """Check if this is a Svalboard and load layer colors."""
        self.is_svalboard = False
        self.sval_layer_colors = None

        if not self.definition:
            return

        name = self.definition.get('name', '')
        if not name.lower().startswith('svalboard'):
            return

        self.is_svalboard = True
        logging.debug("Detected Svalboard")

        # Load layer colors
        self.sval_layer_colors = []
        for layer in range(min(self.layers, 16)):
            data = self._via_get_value(SVAL_ID_LAYER0_COLOR + layer)
            if data is None:
                default_hue = (layer * 20) % 256
                self.sval_layer_colors.append((default_hue, 255))
            else:
                self.sval_layer_colors.append((data[0], data[1]))

    def _via_get_value(self, value_id):
        """Get a custom keyboard value via VIA protocol."""
        data = self.wrapper.send_via(
            struct.pack("BBB", CMD_VIA_CUSTOM_GET_VALUE, 0, value_id),
            retries=20
        )
        if data[0] == 0xFF:
            return None
        return data[3:]

    def get_current_layer(self):
        """Get the currently active layer from the keyboard."""
        if not self.is_svalboard:
            return None
        try:
            data = self._via_get_value(SVAL_ID_CURRENT_LAYER)
            if data:
                return data[0]
        except Exception:
            pass
        return None
