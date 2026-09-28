"""Generate both desktop icon chains from the one approved thinking-guy master."""
from pathlib import Path
from PIL import Image

root = Path(__file__).resolve().parents[1]
master = Image.open(root / 'assets/branding/app-icon-mymind.png').convert('RGBA')
assert master.size == (1024, 1024)
for relative in ('surfaces/gui/src-tauri/icons', 'desktop/src-tauri/icons'):
    target = root / relative
    target.mkdir(parents=True, exist_ok=True)
    master.save(target / 'icon.png')
    master.save(target / 'icon.icns', format='ICNS')
    master.save(target / 'icon.ico', format='ICO')
    for size, filename in [(32, '32x32.png'), (128, '128x128.png'), (256, '128x128@2x.png')]:
        master.resize((size, size), Image.Resampling.LANCZOS).save(target / filename)

# Keep the menu-bar identity in the same asset pipeline as the Dock icon.
tray = master.resize((44, 44), Image.Resampling.LANCZOS)
(root / "surfaces/gui/src-tauri/icons/tray.rgba").write_bytes(tray.tobytes())
tray.save(root / "surfaces/gui/src-tauri/icons/tray.png")
