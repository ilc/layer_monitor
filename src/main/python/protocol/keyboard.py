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
    VIABLE_LAYER_STATE_GET,
    VIABLE_LAYER_STATE_SET,
)

class Keyboard:
    """Simplified keyboard class for layer monitoring."""

    def __init__(self, dev):
        self.dev = dev
        self.wrapper = ClientWrapper(dev)
        self.definition = None
        self.is_svalboard = False
        self.layer_colors = None
        self.layers = 0
        self.viable_protocol = None
        self._menu_ids = {}  # Maps semantic ID to numeric ID

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

    def _extract_menu_ids(self, items):
        """Recursively extract semantic IDs from menu structure."""
        for item in items:
            if isinstance(item, dict):
                # Check if this item has a content array with ID info
                content = item.get('content')
                if isinstance(content, list) and len(content) >= 3:
                    # Format: ["semantic_id", channel, numeric_id]
                    if isinstance(content[0], str) and isinstance(content[2], int):
                        self._menu_ids[content[0]] = content[2]
                elif isinstance(content, list):
                    # Nested content, recurse
                    self._extract_menu_ids(content)

    def _reload_svalboard(self):
        """Load layer colors from definition if available."""
        self.is_svalboard = False
        self.layer_colors = None
        self._menu_ids = {}

        if not self.definition:
            return

        name = self.definition.get('name', '')
        if name.lower().startswith('svalboard'):
            self.is_svalboard = True
            logging.debug("Detected Svalboard")

        # Extract semantic IDs from menus for any Viable keyboard
        menus = self.definition.get('menus', [])
        for menu in menus:
            content = menu.get('content', [])
            self._extract_menu_ids(content)

        logging.debug("Extracted menu IDs: %s", self._menu_ids)

        # Check if layer color IDs are defined
        if 'id_layer0_color' not in self._menu_ids:
            logging.debug("No layer color IDs in definition")
            return

        # Load layer colors using semantic IDs from definition
        self.layer_colors = []
        for layer in range(min(self.layers, 16)):
            semantic_id = f"id_layer{layer}_color"
            numeric_id = self._menu_ids.get(semantic_id)
            if numeric_id is None:
                logging.debug("No ID found for %s, using default", semantic_id)
                default_hue = (layer * 20) % 256
                self.layer_colors.append((default_hue, 255))
            else:
                data = self._via_get_value(numeric_id)
                if data is None:
                    default_hue = (layer * 20) % 256
                    self.layer_colors.append((default_hue, 255))
                else:
                    self.layer_colors.append((data[0], data[1]))

        logging.debug("Loaded %d layer colors", len(self.layer_colors))

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
        """Get the currently active layer from the keyboard.

        Returns the highest active layer from the 32-bit layer state mask.
        Uses the Viable protocol layer_state_get command.
        """
        if not self.viable_protocol:
            return None
        try:
            data = self.wrapper.send_viable(
                struct.pack("B", VIABLE_LAYER_STATE_GET),
                retries=5
            )
            if data[0] == VIABLE_PREFIX and data[1] == VIABLE_LAYER_STATE_GET:
                # Parse 32-bit little-endian layer state mask from data[2:6]
                layer_mask = data[2] | (data[3] << 8) | (data[4] << 16) | (data[5] << 24)
                # Return highest active layer
                if layer_mask == 0:
                    return 0
                return (layer_mask.bit_length() - 1)
        except Exception:
            pass
        return None

    def get_layer_state(self):
        """Get the full 32-bit layer state mask from the keyboard.

        Uses the Viable protocol layer_state_get command.
        """
        if not self.viable_protocol:
            return None
        try:
            data = self.wrapper.send_viable(
                struct.pack("B", VIABLE_LAYER_STATE_GET),
                retries=5
            )
            if data[0] == VIABLE_PREFIX and data[1] == VIABLE_LAYER_STATE_GET:
                # Parse 32-bit little-endian layer state mask from data[2:6]
                return data[2] | (data[3] << 8) | (data[4] << 16) | (data[5] << 24)
        except Exception:
            pass
        return None
