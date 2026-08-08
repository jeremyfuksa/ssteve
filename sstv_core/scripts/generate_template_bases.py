"""Generate the Smart Reply base images the bundled templates reference.

The three template JSONs shipped since Phase 5 reference base PNGs that
were never committed, so TemplateEngine loaded zero templates and every
Smart Reply render 404'd. These bases are deliberately simple generated
graphics (SSTV canvas 320x256): a framed card with zones clear of the
field coordinates declared in the JSONs. Re-run this script to regenerate;
commit the PNGs.

Usage: uv run python scripts/generate_template_bases.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

WIDTH, HEIGHT = 320, 256
OUT_DIR = Path(__file__).resolve().parent.parent / "templates" / "smart_reply"


def _vertical_gradient(top: tuple, bottom: tuple) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT))
    for y in range(HEIGHT):
        t = y / (HEIGHT - 1)
        row = tuple(int(a + (b - a) * t) for a, b in zip(top, bottom))
        for x in range(WIDTH):
            image.putpixel((x, y), row)
    return image


def qsl_card() -> Image.Image:
    """Dark navy card, light border, text zone on the left."""
    image = _vertical_gradient((16, 24, 48), (8, 12, 24))
    draw = ImageDraw.Draw(image)
    draw.rectangle([4, 4, WIDTH - 5, HEIGHT - 5], outline=(124, 255, 138), width=2)
    draw.rectangle([40, 80, 280, 250], fill=(10, 16, 32))
    draw.line([40, 70, 280, 70], fill=(124, 255, 138), width=1)
    return image


def monitor_frame() -> Image.Image:
    """Neutral dark frame with a wide open center."""
    image = _vertical_gradient((28, 28, 32), (12, 12, 16))
    draw = ImageDraw.Draw(image)
    draw.rectangle([2, 2, WIDTH - 3, HEIGHT - 3], outline=(242, 180, 81), width=3)
    draw.rectangle([16, 200, WIDTH - 17, HEIGHT - 17], fill=(20, 20, 24))
    return image


def minimal_badge() -> Image.Image:
    """Plain dark field, single accent bar across the top."""
    image = Image.new("RGB", (WIDTH, HEIGHT), (14, 14, 18))
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, WIDTH, 40], fill=(91, 214, 232))
    return image


GENERATORS = {
    "qsl_card_base.png": qsl_card,
    "monitor_frame_base.png": monitor_frame,
    "minimal_badge_base.png": minimal_badge,
}


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for filename, generator in GENERATORS.items():
        path = OUT_DIR / filename
        generator().save(path, format="PNG")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
