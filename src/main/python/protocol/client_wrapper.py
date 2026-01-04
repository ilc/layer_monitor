# SPDX-License-Identifier: GPL-2.0-or-later
"""
Client ID Protocol Wrapper for layer monitor.

Simplified version that handles client ID lifecycle for keyboard communication.
"""

import os
import struct
import time
import logging

from protocol.constants import VIABLE_PREFIX

# Protocol constants
WRAPPER_PREFIX = 0xDD
CLIENT_ID_BOOTSTRAP = 0x00000000
CLIENT_ID_ERROR = 0xFFFFFFFF

# Error codes
CLIENT_ERR_INVALID_ID = 0x01
CLIENT_ERR_NO_IDS = 0x02
CLIENT_ERR_UNKNOWN_PROTO = 0x03

# Bootstrap nonce size
NONCE_SIZE = 20


class ClientWrapperError(Exception):
    """Exception raised for client wrapper protocol errors."""
    pass


class ClientWrapper:
    """Manages client ID lifecycle and wraps protocol commands."""

    def __init__(self, dev, msg_len=32):
        self.dev = dev
        self.msg_len = msg_len
        self.client_id = None
        self.ttl_seconds = 120
        self.last_bootstrap = 0
        self._renewal_threshold = 0.70

    def reset(self):
        """Reset client state."""
        self.client_id = None
        self.last_bootstrap = 0

    def _needs_renewal(self):
        """Check if client ID needs renewal."""
        if self.client_id is None:
            return True
        age = time.time() - self.last_bootstrap
        return age >= (self.ttl_seconds * self._renewal_threshold)

    def bootstrap(self, retries=5):
        """Bootstrap to get a new client ID from the keyboard."""
        nonce = os.urandom(NONCE_SIZE)

        msg = struct.pack("<BI", WRAPPER_PREFIX, CLIENT_ID_BOOTSTRAP) + nonce
        msg = msg + b"\x00" * (self.msg_len - len(msg))

        for attempt in range(retries):
            try:
                written = self.dev.write(b"\x00" + msg)
                if written != self.msg_len + 1:
                    time.sleep(0.1)
                    continue

                response = bytes(self.dev.read(self.msg_len, timeout_ms=500))
                if not response:
                    time.sleep(0.1)
                    continue

                if response[0] != WRAPPER_PREFIX:
                    continue

                resp_id = struct.unpack("<I", response[1:5])[0]
                if resp_id != CLIENT_ID_BOOTSTRAP:
                    continue

                resp_nonce = response[5:5 + NONCE_SIZE]
                if resp_nonce != nonce:
                    continue

                new_id = struct.unpack("<I", response[25:29])[0]
                if new_id == CLIENT_ID_ERROR:
                    error_code = response[29]
                    raise ClientWrapperError(f"Bootstrap failed with error code {error_code}")

                ttl = struct.unpack("<H", response[29:31])[0]

                self.client_id = new_id
                self.ttl_seconds = ttl
                self.last_bootstrap = time.time()
                logging.debug("bootstrap: got client ID 0x%08X, TTL %d seconds", new_id, ttl)
                return True

            except OSError as e:
                logging.debug("bootstrap attempt %d failed: %s", attempt + 1, e)
                time.sleep(0.1)

        raise ClientWrapperError("Bootstrap failed after all retries")

    def _ensure_client_id(self):
        """Ensure we have a valid client ID."""
        if self._needs_renewal():
            self.bootstrap()

    def send_via(self, command, retries=20, read_timeout_ms=500):
        """Send a VIA protocol command wrapped with client ID."""
        VIA_PROTOCOL = 0xFE

        self._ensure_client_id()

        msg = struct.pack("<BIB", WRAPPER_PREFIX, self.client_id, VIA_PROTOCOL) + command
        msg = msg + b"\x00" * (self.msg_len - len(msg))

        for attempt in range(retries):
            try:
                written = self.dev.write(b"\x00" + msg)
                if written != self.msg_len + 1:
                    time.sleep(0.1)
                    continue

                for _ in range(50):
                    response = bytes(self.dev.read(self.msg_len, timeout_ms=read_timeout_ms))
                    if not response:
                        break

                    if response[0] != WRAPPER_PREFIX:
                        continue

                    resp_id = struct.unpack("<I", response[1:5])[0]

                    if resp_id != self.client_id:
                        continue

                    if response[5] == 0xFF:
                        error_code = response[6]
                        if error_code == CLIENT_ERR_INVALID_ID:
                            self.bootstrap()
                            msg = struct.pack("<BIB", WRAPPER_PREFIX, self.client_id, VIA_PROTOCOL) + command
                            msg = msg + b"\x00" * (self.msg_len - len(msg))
                            break
                        else:
                            raise ClientWrapperError(f"Protocol error code {error_code}")

                    if response[5] != VIA_PROTOCOL:
                        continue

                    return response[6:]

            except OSError as e:
                logging.debug("send_via attempt %d failed: %s", attempt + 1, e)
                time.sleep(0.1)

        raise ClientWrapperError("Failed to communicate after all retries")

    def send_viable(self, command, retries=20, read_timeout_ms=500):
        """Send a Viable protocol command wrapped with client ID."""
        self._ensure_client_id()

        msg = struct.pack("<BI", WRAPPER_PREFIX, self.client_id) + bytes([VIABLE_PREFIX]) + command
        msg = msg + b"\x00" * (self.msg_len - len(msg))

        for attempt in range(retries):
            try:
                written = self.dev.write(b"\x00" + msg)
                if written != self.msg_len + 1:
                    time.sleep(0.1)
                    continue

                for _ in range(50):
                    response = bytes(self.dev.read(self.msg_len, timeout_ms=read_timeout_ms))
                    if not response:
                        break

                    if response[0] != WRAPPER_PREFIX:
                        continue

                    resp_id = struct.unpack("<I", response[1:5])[0]

                    if resp_id != self.client_id:
                        continue

                    if response[5] == 0xFF:
                        error_code = response[6]
                        if error_code == CLIENT_ERR_INVALID_ID:
                            self.bootstrap()
                            msg = struct.pack("<BI", WRAPPER_PREFIX, self.client_id) + bytes([VIABLE_PREFIX]) + command
                            msg = msg + b"\x00" * (self.msg_len - len(msg))
                            break
                        else:
                            raise ClientWrapperError(f"Protocol error code {error_code}")

                    if response[5] != VIABLE_PREFIX:
                        continue

                    return response[5:]

            except OSError as e:
                logging.debug("send_viable attempt %d failed: %s", attempt + 1, e)
                time.sleep(0.1)

        raise ClientWrapperError("Failed to communicate after all retries")
