from __future__ import annotations

import threading
import time
from PIL import Image, ImageDraw
import pystray  # type: ignore[import-untyped]

from usagedash.config import load_config
from usagedash.tray.bridge import summary_line


def _create_icon() -> Image.Image:
    size = (64, 64)
    image = Image.new("RGB", size, (22, 28, 54))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((8, 8, 56, 56), radius=10, fill=(52, 80, 170))
    draw.text((18, 18), "U", fill=(235, 242, 255))
    return image


def run_tray() -> None:
    cfg = load_config()
    icon = pystray.Icon("usagedash", _create_icon(), "UsageDash", menu=pystray.Menu(
        pystray.MenuItem("Quit", lambda icon, item: icon.stop()),
    ))

    def refresh_loop() -> None:
        while icon.visible:
            icon.title = summary_line(cfg.general.windows_state_path)
            time.sleep(max(5, cfg.tray.poll_seconds))

    t = threading.Thread(target=refresh_loop, daemon=True)
    t.start()
    icon.run()
