#!/usr/bin/env python3
"""Build script for Layer Monitor using Nuitka."""

import subprocess
import sys

INFO_PLIST = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>main</string>
    <key>CFBundleIdentifier</key>
    <string>com.viable.layermonitor</string>
    <key>CFBundleName</key>
    <string>LayerMonitor</string>
    <key>CFBundleDisplayName</key>
    <string>Layer Monitor</string>
    <key>CFBundleVersion</key>
    <string>1.0.0</string>
    <key>LSUIElement</key>
    <true/>
</dict>
</plist>
"""

def build():
    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--onefile",
        "--enable-plugin=pyside6",
        "--output-dir=dist",
        "src/main/python/main.py",
    ]

    if sys.platform == "darwin":
        cmd.extend([
            "--macos-create-app-bundle",
            "--macos-app-name=LayerMonitor",
        ])
    elif sys.platform == "win32":
        cmd.append("--windows-console-mode=disable")

    print("Building with:", " ".join(cmd))
    subprocess.run(cmd, check=True)

    # Create Info.plist for macOS (LSUIElement hides from dock)
    if sys.platform == "darwin":
        plist_path = "dist/main.app/Contents/Info.plist"
        with open(plist_path, "w") as f:
            f.write(INFO_PLIST)
        print(f"Created {plist_path}")
        print("\nBuild complete! App at: dist/main.app")
    else:
        print("\nBuild complete!")

if __name__ == "__main__":
    build()
