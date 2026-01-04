#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""
Layer Monitor - System tray application that displays the current keyboard layer.
"""

import os
import sys
import logging
from pathlib import Path

# Hide from dock on macOS (must be set before QApplication)
if sys.platform == "darwin":
    os.environ['QT_MAC_DISABLE_FOREGROUND_APPLICATION_TRANSFORM'] = '1'

from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont
from PySide6.QtCore import Qt, QTimer

from device import find_viable_devices, KeyboardDevice


class AutoStart:
    """Cross-platform auto-start management."""

    APP_NAME = "LayerMonitor"

    @classmethod
    def get_executable_path(cls):
        """Get the path to the running executable."""
        if getattr(sys, 'frozen', False):
            # Running as compiled executable
            exe = sys.executable
            if sys.platform == "darwin":
                # For .app bundle, get the .app path
                # exe is like /path/to/App.app/Contents/MacOS/main
                app_path = Path(exe).parent.parent.parent
                if app_path.suffix == ".app":
                    return str(app_path)
            return exe
        else:
            # Running as script - use python + script path
            return f'"{sys.executable}" "{os.path.abspath(__file__)}"'

    @classmethod
    def is_enabled(cls):
        """Check if auto-start is enabled."""
        if sys.platform == "darwin":
            plist_path = Path.home() / "Library/LaunchAgents/com.viable.layermonitor.plist"
            return plist_path.exists()
        elif sys.platform == "win32":
            try:
                import winreg
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run",
                    0, winreg.KEY_READ
                )
                try:
                    winreg.QueryValueEx(key, cls.APP_NAME)
                    return True
                except FileNotFoundError:
                    return False
                finally:
                    winreg.CloseKey(key)
            except Exception:
                return False
        else:  # Linux
            desktop_path = Path.home() / ".config/autostart/layermonitor.desktop"
            return desktop_path.exists()

    @classmethod
    def enable(cls):
        """Enable auto-start."""
        exe_path = cls.get_executable_path()

        if sys.platform == "darwin":
            plist_dir = Path.home() / "Library/LaunchAgents"
            plist_dir.mkdir(parents=True, exist_ok=True)
            plist_path = plist_dir / "com.viable.layermonitor.plist"

            plist_content = f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.viable.layermonitor</string>
    <key>ProgramArguments</key>
    <array>
        <string>open</string>
        <string>-a</string>
        <string>{exe_path}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
"""
            plist_path.write_text(plist_content)
            logging.info("Auto-start enabled: %s", plist_path)

        elif sys.platform == "win32":
            try:
                import winreg
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run",
                    0, winreg.KEY_SET_VALUE
                )
                winreg.SetValueEx(key, cls.APP_NAME, 0, winreg.REG_SZ, exe_path)
                winreg.CloseKey(key)
                logging.info("Auto-start enabled in registry")
            except Exception as e:
                logging.error("Failed to enable auto-start: %s", e)

        else:  # Linux
            autostart_dir = Path.home() / ".config/autostart"
            autostart_dir.mkdir(parents=True, exist_ok=True)
            desktop_path = autostart_dir / "layermonitor.desktop"

            desktop_content = f"""\
[Desktop Entry]
Type=Application
Name=Layer Monitor
Exec={exe_path}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
"""
            desktop_path.write_text(desktop_content)
            logging.info("Auto-start enabled: %s", desktop_path)

    @classmethod
    def disable(cls):
        """Disable auto-start."""
        if sys.platform == "darwin":
            plist_path = Path.home() / "Library/LaunchAgents/com.viable.layermonitor.plist"
            if plist_path.exists():
                plist_path.unlink()
                logging.info("Auto-start disabled")

        elif sys.platform == "win32":
            try:
                import winreg
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run",
                    0, winreg.KEY_SET_VALUE
                )
                try:
                    winreg.DeleteValue(key, cls.APP_NAME)
                except FileNotFoundError:
                    pass
                winreg.CloseKey(key)
                logging.info("Auto-start disabled")
            except Exception as e:
                logging.error("Failed to disable auto-start: %s", e)

        else:  # Linux
            desktop_path = Path.home() / ".config/autostart/layermonitor.desktop"
            if desktop_path.exists():
                desktop_path.unlink()
                logging.info("Auto-start disabled")

    @classmethod
    def toggle(cls):
        """Toggle auto-start and return new state."""
        if cls.is_enabled():
            cls.disable()
            return False
        else:
            cls.enable()
            return True


# Default layer colors (HSV) - matches GUI
DEFAULT_LAYER_COLORS = [
    (85, 255, 255),   # Green
    (21, 255, 255),   # Orange
    (149, 255, 255),  # Azure
    (0, 255, 255),    # Red
    (170, 255, 255),  # Blue
    (64, 255, 255),   # Chartreuse
    (234, 255, 255),  # Rose
    (32, 255, 255),   # Gold
    (191, 255, 128),  # Purple
    (11, 176, 255),   # Coral
    (106, 255, 255),  # Spring Green
    (128, 255, 128),  # Teal
    (128, 255, 255),  # Turquoise
    (43, 255, 255),   # Yellow
    (213, 255, 255),  # Magenta
    (0, 0, 255),      # White
]


class LayerMonitor:
    """System tray layer monitor application."""

    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        self.device = None
        self.current_layer = -1
        self.layer_icons = {}

        # Initialize layer icons with default colors
        self._init_layer_icons()

        # Create system tray icon
        self.tray_icon = QSystemTrayIcon()
        self.tray_icon.setIcon(self.layer_icons.get(0, QIcon()))
        self.tray_icon.setToolTip("Layer Monitor - Searching for keyboard...")

        # Create context menu
        self.menu = QMenu()
        self.status_action = self.menu.addAction("Searching for keyboard...")
        self.status_action.setEnabled(False)
        self.menu.addSeparator()
        self.autostart_action = self.menu.addAction(self._autostart_label())
        self.autostart_action.triggered.connect(self._toggle_autostart)
        self.menu.addSeparator()
        quit_action = self.menu.addAction("Quit")
        quit_action.triggered.connect(self.quit)
        self.tray_icon.setContextMenu(self.menu)

        # Show menu on left-click too
        self.tray_icon.activated.connect(self._on_tray_activated)

        # Set up polling timers
        self.device_poll_timer = QTimer()
        self.device_poll_timer.timeout.connect(self._poll_device)
        self.device_poll_timer.start(2000)  # Check for device every 2 seconds

        self.layer_poll_timer = QTimer()
        self.layer_poll_timer.timeout.connect(self._poll_layer)
        self.layer_poll_timer.start(200)  # Poll layer every 200ms

        # Initial device search
        self._poll_device()

        self.tray_icon.show()

    def _init_layer_icons(self):
        """Initialize layer icons with default colors."""
        for layer in range(16):
            h, s, v = DEFAULT_LAYER_COLORS[layer]
            self.layer_icons[layer] = self._create_layer_icon(layer, h, s, v)

    def _create_layer_icon(self, layer, h, s, v):
        """Create a 32x32 icon with layer number on colored background."""
        pixmap = QPixmap(32, 32)
        color = QColor.fromHsv(h, s, v)
        pixmap.fill(color)

        painter = QPainter(pixmap)
        # Use contrasting text color
        brightness = (color.red() * 299 + color.green() * 587 + color.blue() * 114) / 1000
        text_color = Qt.black if brightness > 128 else Qt.white
        painter.setPen(text_color)
        font = QFont()
        font.setPixelSize(20)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, str(layer))
        painter.end()

        return QIcon(pixmap)

    def _on_tray_activated(self, reason):
        """Handle tray icon activation (click)."""
        if reason == QSystemTrayIcon.Trigger:  # Left click
            self.menu.popup(self.tray_icon.geometry().center())

    def _autostart_label(self):
        """Get menu label for autostart toggle."""
        check = "✓ " if AutoStart.is_enabled() else "  "
        return check + "Start at Login"

    def _toggle_autostart(self):
        """Toggle auto-start setting."""
        AutoStart.toggle()
        self.autostart_action.setText(self._autostart_label())

    def _update_layer_icons_from_keyboard(self):
        """Update layer icons using colors from connected keyboard."""
        if not self.device:
            return

        colors = self.device.get_layer_colors()
        if colors:
            for layer, (h, s) in enumerate(colors):
                # V defaults to 255 for display
                self.layer_icons[layer] = self._create_layer_icon(layer, h, s, 255)

    def _poll_device(self):
        """Check for keyboard connection."""
        if self.device:
            # Check if device is still connected
            try:
                layer = self.device.get_current_layer()
                if layer is None:
                    raise Exception("Device disconnected")
            except Exception:
                logging.info("Keyboard disconnected")
                self.device.close()
                self.device = None
                self.current_layer = -1
                self.status_action.setText("Searching for keyboard...")
                self.tray_icon.setToolTip("Layer Monitor - Searching for keyboard...")
                # Reset to default colors
                self._init_layer_icons()
                return

        if not self.device:
            # Search for a new device
            devices = find_viable_devices(quiet=True)
            if devices:
                try:
                    self.device = KeyboardDevice(devices[0])
                    self.device.open()
                    logging.info("Connected to: %s", self.device.title())
                    self.status_action.setText(f"Connected: {self.device.title()}")
                    # Update icons with keyboard colors
                    self._update_layer_icons_from_keyboard()
                except Exception as e:
                    logging.warning("Failed to open device: %s", e)
                    self.device = None

    def _poll_layer(self):
        """Poll the keyboard for current layer and update tray icon."""
        if not self.device:
            return

        try:
            layer = self.device.get_current_layer()
            if layer is None:
                return

            if layer != self.current_layer:
                self.current_layer = layer
                if layer in self.layer_icons:
                    self.tray_icon.setIcon(self.layer_icons[layer])
                    self.tray_icon.setToolTip(f"Layer {layer}")
        except Exception as e:
            logging.debug("Layer poll error: %s", e)

    def quit(self):
        """Clean up and quit the application."""
        if self.device:
            self.device.close()
        self.tray_icon.hide()
        self.app.quit()

    def run(self):
        """Run the application event loop."""
        return self.app.exec()


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    monitor = LayerMonitor()

    # Check for system tray support (must be after QApplication creation)
    if not QSystemTrayIcon.isSystemTrayAvailable():
        logging.error("System tray not available")
        return 1

    return monitor.run()


if __name__ == "__main__":
    sys.exit(main())
