"""Draws the square-ish (4:5) image Instagram needs for each post."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTS = Path(__file__).resolve().parent / "fonts"
W, H = 1080, 1350  # Instagram's preferred portrait size
MARGIN = 104

# (background, text, accent) per topic: calm, muted colors that look good in a grid.
PALETTES = {
    "portland_events": ("#1f3d34", "#f3ead8", "#d9a441"),
    "portland_local": ("#2c3e50", "#eef1f3", "#8fb3c9"),
    "chicago_local": ("#7a2e26", "#f7ece4", "#e9b8a5"),
    "cats": ("#e8d9c4", "#2b2420", "#b5652e"),
    "clothing": ("#3a3a34", "#efece4", "#b9a77a"),
    "wellness": ("#dfe7dc", "#22332a", "#6f9a7c"),
}
LABELS = {
    "portland_events": "Portland, this week",
    "portland_local": "Portland",
    "chicago_local": "Chicago, from afar",
    "cats": "Cat thoughts",
    "clothing": "Rain-ready",
    "wellness": "Small reminder",
}

SERIF_CANDIDATES = [
    FONTS / "Fraunces.ttf",
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"),
    Path("/usr/share/fonts/truetype/freefont/FreeSerif.ttf"),
]
SANS_CANDIDATES = [
    FONTS / "Inter.ttf",
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/freefont/FreeSans.ttf"),
]


def _font(candidates: list[Path], size: int, weight: int | None = None) -> ImageFont.FreeTypeFont:
    for path in candidates:
        if path.exists():
            f = ImageFont.truetype(str(path), size)
            if weight is not None:
                try:  # variable fonts: pick a weight; static fonts just ignore this
                    axes = f.get_variation_axes()
                    f.set_variation_by_axes(
                        [weight if a.get("name", b"") in (b"Weight", "Weight") else a["default"] for a in axes]
                    )
                except Exception:
                    pass
            return f
    return ImageFont.load_default(size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= max_w or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def make_card(text: str, topic: str, out: Path) -> Path:
    bg, ink, accent = PALETTES.get(topic, PALETTES["portland_local"])
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)
    max_w = W - 2 * MARGIN
    max_h = H - 2 * MARGIN - 220  # leave room for the label at the bottom

    # Largest text size that fits.
    for size in range(104, 39, -4):
        font = _font(SERIF_CANDIDATES, size, weight=500)
        lines = _wrap(d, text, font, max_w)
        line_h = int(size * 1.22)
        if len(lines) * line_h <= max_h and all(d.textlength(l, font=font) <= max_w for l in lines):
            break

    block_h = len(lines) * line_h
    y = MARGIN + 80 + (max_h - block_h) // 2
    d.rectangle([MARGIN, y - 64, MARGIN + 96, y - 56], fill=accent)  # small accent bar
    for l in lines:
        d.text((MARGIN, y), l, font=font, fill=ink)
        y += line_h

    label_font = _font(SANS_CANDIDATES, 34, weight=600)
    label = LABELS.get(topic, "").upper()
    d.text((MARGIN, H - MARGIN - 34), label, font=label_font, fill=accent)

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "JPEG", quality=90, optimize=True)
    return out
