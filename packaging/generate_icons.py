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
