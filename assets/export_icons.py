"""Exports the PocketMind master icon (assets/icon_master.png) into the
platform-specific formats PyInstaller's --icon flag needs:
  - assets/icon.ico   (Windows, multi-resolution)
  - assets/PocketMind.iconset/*.png  (macOS iconset — iconutil turns this
    into a .icns at build time; iconutil itself only exists on macOS, so
    that conversion step lives in build_macos.sh, not here)
  - assets/icon_256.png  (Linux — for a .desktop file's Icon= entry)
"""
from pathlib import Path
from PIL import Image

ASSETS = Path(__file__).resolve().parent
master = Image.open(ASSETS / "icon_master.png").convert("RGBA")

# --- Windows .ico ---
ico_sizes = [16, 24, 32, 48, 64, 128, 256]
master.save(ASSETS / "icon.ico", sizes=[(s, s) for s in ico_sizes])
print("wrote", ASSETS / "icon.ico", "with sizes", ico_sizes)

# --- macOS .iconset (per Apple's required naming) ---
iconset_dir = ASSETS / "PocketMind.iconset"
iconset_dir.mkdir(exist_ok=True)
mac_sizes = [16, 32, 128, 256, 512, 1024]  # Apple's exact iconset base sizes — iconutil rejects anything else
for size in mac_sizes:
    img = master.resize((size, size), Image.LANCZOS)
    if size == 1024:
        img.save(iconset_dir / "icon_512x512@2x.png")
        continue
    img.save(iconset_dir / f"icon_{size}x{size}.png")
    img2x = master.resize((size * 2, size * 2), Image.LANCZOS)
    img2x.save(iconset_dir / f"icon_{size}x{size}@2x.png")
print("wrote", iconset_dir, "with", len(list(iconset_dir.iterdir())), "files")

# --- Linux desktop icon ---
master.resize((256, 256), Image.LANCZOS).save(ASSETS / "icon_256.png")
print("wrote", ASSETS / "icon_256.png")
