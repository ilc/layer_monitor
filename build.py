#!/usr/bin/env python3
"""Build script for Layer Monitor using Nuitka."""

import subprocess
import sys
import os
import tempfile

# Layer 0 color (Green) in HSV
LAYER_0_HSV = (85, 255, 255)


def hsv_to_rgb(h, s, v):
    """Convert HSV (0-255 scale for s,v and 0-255 for h) to RGB."""
    # Convert to 0-1 scale
    h = h / 255.0 * 360
    s = s / 255.0
    v = v / 255.0

    c = v * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = v - c

    if h < 60:
        r, g, b = c, x, 0
    elif h < 120:
        r, g, b = x, c, 0
    elif h < 180:
        r, g, b = 0, c, x
    elif h < 240:
        r, g, b = 0, x, c
    elif h < 300:
        r, g, b = x, 0, c
    else:
        r, g, b = c, 0, x

    return int((r + m) * 255), int((g + m) * 255), int((b + m) * 255)


def create_icon_png(size, output_path):
    """Create a PNG icon with '0' on green background."""
    from PIL import Image, ImageDraw, ImageFont

    h, s, v = LAYER_0_HSV
    r, g, b = hsv_to_rgb(h, s, v)

    img = Image.new('RGB', (size, size), (r, g, b))
    draw = ImageDraw.Draw(img)

    # Calculate font size (roughly 60% of icon size)
    font_size = int(size * 0.6)

    # Try to use a bold system font (cross-platform)
    font = None
    font_paths = []
    if sys.platform == "darwin":
        font_paths = ['/System/Library/Fonts/Helvetica.ttc',
                      '/System/Library/Fonts/SFNSDisplay.ttf',
                      '/Library/Fonts/Arial Bold.ttf']
    elif sys.platform == "win32":
        font_paths = ['C:/Windows/Fonts/arialbd.ttf',
                      'C:/Windows/Fonts/arial.ttf',
                      'C:/Windows/Fonts/segoeui.ttf']
    else:  # Linux
        font_paths = ['/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
                      '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
                      '/usr/share/fonts/TTF/DejaVuSans-Bold.ttf']

    for font_name in font_paths:
        try:
            font = ImageFont.truetype(font_name, font_size)
            break
        except (OSError, IOError):
            continue

    if font is None:
        font = ImageFont.load_default()

    # Calculate text color (black for bright backgrounds)
    brightness = (r * 299 + g * 587 + b * 114) / 1000
    text_color = (0, 0, 0) if brightness > 128 else (255, 255, 255)

    # Center the text
    text = "0"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (size - text_width) // 2
    y = (size - text_height) // 2 - bbox[1]

    draw.text((x, y), text, fill=text_color, font=font)
    img.save(output_path, 'PNG')


def create_macos_icns(output_path):
    """Create a macOS .icns file."""
    # Icon sizes required for .icns
    sizes = [16, 32, 64, 128, 256, 512, 1024]

    with tempfile.TemporaryDirectory() as tmpdir:
        iconset_dir = os.path.join(tmpdir, 'AppIcon.iconset')
        os.makedirs(iconset_dir)

        for size in sizes:
            # Standard resolution
            create_icon_png(size, os.path.join(iconset_dir, f'icon_{size}x{size}.png'))
            # Retina resolution (2x)
            if size <= 512:
                create_icon_png(size * 2, os.path.join(iconset_dir, f'icon_{size}x{size}@2x.png'))

        # Use iconutil to create .icns
        subprocess.run(['iconutil', '-c', 'icns', iconset_dir, '-o', output_path], check=True)
        print(f"Created {output_path}")


def create_windows_ico(output_path):
    """Create a Windows .ico file."""
    from PIL import Image

    # Windows icon sizes
    sizes = [16, 32, 48, 64, 128, 256]
    images = []

    with tempfile.TemporaryDirectory() as tmpdir:
        for size in sizes:
            png_path = os.path.join(tmpdir, f'icon_{size}.png')
            create_icon_png(size, png_path)
            img = Image.open(png_path)
            images.append(img)

        # Save as ICO with multiple sizes
        images[0].save(output_path, format='ICO', sizes=[(s, s) for s in sizes],
                       append_images=images[1:])
        print(f"Created {output_path}")


def create_linux_png(output_path):
    """Create a PNG icon for Linux."""
    create_icon_png(256, output_path)
    print(f"Created {output_path}")


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
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>LSUIElement</key>
    <true/>
</dict>
</plist>
"""

def build():
    os.makedirs("dist", exist_ok=True)

    # Generate platform-specific icon before build
    icon_arg = None
    if sys.platform == "darwin":
        pass  # macOS icon is added post-build to app bundle
    elif sys.platform == "win32":
        ico_path = "dist/AppIcon.ico"
        create_windows_ico(ico_path)
        icon_arg = f"--windows-icon-from-ico={ico_path}"
    else:  # Linux
        png_path = "dist/AppIcon.png"
        create_linux_png(png_path)
        icon_arg = f"--linux-icon={png_path}"

    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--onefile",
        "--enable-plugin=pyside6",
        "--output-dir=dist",
        "src/main/python/main.py",
    ]

    if icon_arg:
        cmd.append(icon_arg)

    if sys.platform == "darwin":
        cmd.extend([
            "--macos-create-app-bundle",
            "--macos-app-name=LayerMonitor",
        ])
    elif sys.platform == "win32":
        cmd.append("--windows-console-mode=disable")

    print("Building with:", " ".join(cmd))
    subprocess.run(cmd, check=True)

    # Create Info.plist and icon for macOS (LSUIElement hides from dock)
    if sys.platform == "darwin":
        plist_path = "dist/main.app/Contents/Info.plist"
        with open(plist_path, "w") as f:
            f.write(INFO_PLIST)
        print(f"Created {plist_path}")

        # Create Resources directory and app icon
        resources_dir = "dist/main.app/Contents/Resources"
        os.makedirs(resources_dir, exist_ok=True)
        icon_path = os.path.join(resources_dir, "AppIcon.icns")
        create_macos_icns(icon_path)

        print("\nBuild complete! App at: dist/main.app")
    else:
        print("\nBuild complete!")

if __name__ == "__main__":
    build()
