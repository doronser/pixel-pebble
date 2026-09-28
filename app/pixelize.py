import colorsys
import math
import random
from datetime import date

from PIL import Image, ImageDraw, ImageFont, ImageOps

# Grid resolution the art is designed at, before blocky upscale. Both divide
# AVATAR_BOX (160) evenly so every pixel-art "pixel" is the same size on the
# watch — a non-integer scale makes some blocks 2px wide and others 3px.
RAW_PHOTO_GRID = 40   # ×4: raw photos have far more color/detail noise than
                      # a hardware sprite should, so crush it hard
STYLIZED_GRID = 80    # ×2: Kling's output is already pixel-art-ish, this just
                      # cleans up JPEG/AI shading noise into flat blocks

RAW_PHOTO_COLORS = 32  # posterize messy photos before snapping to the Pebble
                       # palette, so they read as retro art rather than noise

MIN_ACCENT_LUMA = 110

# Pebble's 64-color hardware palette: each channel is one of 4 levels.
PEBBLE_LEVELS = (0x00, 0x55, 0xAA, 0xFF)


def _pebble_palette_image() -> Image.Image:
    pal = [c for r in PEBBLE_LEVELS for g in PEBBLE_LEVELS for b in PEBBLE_LEVELS for c in (r, g, b)]
    img = Image.new("P", (1, 1))
    img.putpalette(pal + [0] * (768 - len(pal)))
    return img


PEBBLE_PALETTE = _pebble_palette_image()


def snap_to_pebble(img: Image.Image) -> Image.Image:
    """Map every pixel to the nearest Pebble color, so the web preview is
    exactly what the watch will show (the SDK would otherwise do this snap
    itself at build time, after the user already approved the preview)."""
    return img.convert("RGB").quantize(palette=PEBBLE_PALETTE, dither=Image.Dither.NONE)


def load_oriented(path: str) -> Image.Image:
    """Open an image with its EXIF rotation applied — phone photos are often
    stored sideways with an orientation tag that Image.open ignores."""
    return ImageOps.exif_transpose(Image.open(path)).convert("RGB")


def center_crop_square(img: Image.Image) -> Image.Image:
    side = min(img.size)
    left = (img.width - side) // 2
    top = (img.height - side) // 2
    return img.crop((left, top, left + side, top + side))


def pixelize(input_path: str, output_path: str, box_size: int, source_is_stylized: bool = False) -> None:
    """Downsample to a small grid, then upscale with nearest-neighbor so the
    result reads as blocky pixel art instead of a smoothed-down photo.

    source_is_stylized=True skips the harsh color quantization (for images
    that already came back from Kling as pixel art — re-quantizing an
    already-limited palette just muddies it) and uses a finer grid so more
    of Kling's detail survives the blocky-ification.
    """
    img = load_oriented(input_path)
    # Uploads are cropped square in the browser and Kling is asked for 1:1,
    # so this is only a safety net for API clients that skip the cropper.
    img = center_crop_square(img)

    grid = STYLIZED_GRID if source_is_stylized else RAW_PHOTO_GRID
    small = img.resize((grid, grid), Image.BOX)

    if not source_is_stylized:
        small = small.quantize(colors=RAW_PHOTO_COLORS, method=Image.MEDIANCUT).convert("RGB")

    blocky = snap_to_pebble(small).resize((box_size, box_size), Image.NEAREST)
    blocky.convert("RGB").save(output_path, "PNG")


def extract_accent_color(image_path: str) -> tuple[int, int, int]:
    """Pick a vibrant accent color from the image for the watch's time text.
    A plain average tends toward muddy gray/brown, so instead: quantize down
    to a handful of colors and pick the most saturated one in a sane
    brightness range, weighted by how much of the image it covers. Falls
    back to white if nothing qualifies (e.g. a near-grayscale image).

    The result is snapped to the Pebble palette, and dark picks are lifted
    so the text stays readable on the black background."""
    img = Image.open(image_path).convert("RGB").resize((50, 50))
    quantized = img.quantize(colors=8, method=Image.MEDIANCUT)
    palette = quantized.getpalette()

    candidates = []
    for count, idx in quantized.getcolors():
        r, g, b = palette[idx * 3:idx * 3 + 3]
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if s > 0.35 and 0.2 < v < 0.95:
            candidates.append((s, count, (r, g, b)))

    if not candidates:
        return (255, 255, 255)

    candidates.sort(key=lambda c: (-c[0], -c[1]))
    r, g, b = snap_to_pebble(Image.new("RGB", (1, 1), candidates[0][2])).convert("RGB").getpixel((0, 0))
    # Lift every channel a palette step at a time until it's bright enough
    # to read on black (a dark navy pick is technically vibrant, not legible).
    while 0.299 * r + 0.587 * g + 0.114 * b < MIN_ACCENT_LUMA:
        r, g, b = (min(0xFF, c + 0x55) for c in (r, g, b))
    return (r, g, b)


# --- Tap animation -----------------------------------------------------------
# The watch plays these frames (as an APNG resource, via GBitmapSequence) when
# the wrist is flicked: a diagonal "shine" sweeps across the sprite, then a few
# sparkles twinkle around it. Frame 0 is the untouched avatar, so the watch can
# show the first frame as its resting state. Everything stays on the Pebble
# palette so the watch never has to re-quantize.

SHINE_FRAMES = 7
SPARKLE_FRAMES = 4
FRAME_MS = 70


def _lighten(rgb: tuple[int, int, int], levels: int) -> tuple[int, int, int]:
    return tuple(min(0xFF, c + 0x55 * levels) for c in rgb)


def _sparkle(draw: ImageDraw.ImageDraw, cx: int, cy: int, size: int, color) -> None:
    # A 4-point pixel star, drawn in 2px blocks to match the ×2 sprite grid.
    for i in range(-size, size + 1):
        draw.rectangle((cx + i * 2, cy, cx + i * 2 + 1, cy + 1), fill=color)
        draw.rectangle((cx, cy + i * 2, cx + 1, cy + i * 2 + 1), fill=color)


def make_animation_frames(avatar_path: str, seed: str = "") -> list[Image.Image]:
    base = Image.open(avatar_path).convert("RGB")
    w, h = base.size
    px = base.load()
    frames = [base.copy()]

    band = w // 4
    for f in range(SHINE_FRAMES):
        frame = base.copy()
        fpx = frame.load()
        # The band's center moves from off the top-left to off the bottom-right.
        pos = -band + (w + h + band) * (f + 1) // (SHINE_FRAMES + 1)
        for y in range(0, h, 2):
            for x in range(0, w, 2):
                d = abs((x + y) - pos)
                if d < band // 2:
                    c = _lighten(px[x, y], 2 if d < band // 6 else 1)
                    for dy in (0, 1):
                        for dx in (0, 1):
                            fpx[x + dx, y + dy] = c
        frames.append(frame)

    rng = random.Random(seed)
    spots = [(rng.randrange(12, w - 12) & ~1, rng.randrange(12, h - 12) & ~1) for _ in range(3)]
    sizes = [(1, 0, 0), (2, 1, 0), (1, 2, 1), (0, 1, 2)]
    for f in range(SPARKLE_FRAMES):
        frame = base.copy()
        draw = ImageDraw.Draw(frame)
        for (cx, cy), size in zip(spots, sizes[f]):
            if size:
                _sparkle(draw, cx, cy, size, (255, 255, 255) if size > 1 else (255, 255, 170))
        frames.append(frame)

    frames.append(base.copy())
    return frames


def save_apng(frames: list[Image.Image], output_path: str, durations: list[int] | int, loop: int) -> None:
    """Save as a palettized APNG with full-frame replacement (no disposal or
    blend tricks) — the simplest form for Pebble's on-watch decoder."""
    # Pebble's decoder rejects a padded 256-entry PLTE, so shrink the palette
    # to just the colors the frames actually use (at most 64).
    snapped = [snap_to_pebble(f) for f in frames]
    used = sorted({i for f in snapped for _, i in f.getcolors(256)})
    remap = {old: new for new, old in enumerate(used)}
    full = snapped[0].getpalette()
    palette = [c for i in used for c in full[i * 3:i * 3 + 3]]
    snapped = [f.point(lambda i: remap.get(i, 0)) for f in snapped]
    for f in snapped:
        f.putpalette(palette)
    snapped[0].save(
        output_path,
        format="PNG",
        save_all=True,
        append_images=snapped[1:],
        duration=durations,
        loop=loop,
        disposal=0,
        blend=0,
        default_image=False,
        optimize=False,
    )


# --- Web preview of the whole watchface --------------------------------------
# Mirrors the layout in watchface-template/src/c/main.c.template. Keep the
# numbers in sync — this is what the user approves before building.

SCREEN_W, SCREEN_H = 200, 228
STATUS_H = 22
AVATAR_Y = 24
TIME_Y = 190


def _draw_battery(draw: ImageDraw.ImageDraw, x: int, y: int, percent: int, accent) -> None:
    draw.rectangle((x, y, x + 23, y + 11), outline=(255, 255, 255), width=2)
    draw.rectangle((x + 24, y + 3, x + 25, y + 8), fill=(255, 255, 255))
    segments = max(1, math.ceil(percent / 25))
    color = (255, 0, 0) if percent <= 20 else accent
    for i in range(segments):
        draw.rectangle((x + 4 + i * 4 + i, y + 4, x + 7 + i * 4 + i, y + 7), fill=color)


def render_face_mockup(avatar_path: str, output_path: str, accent: tuple[int, int, int], font_path: str,
                       frames: list[Image.Image] | None = None) -> None:
    """Render the full watchface (status bar + avatar + time) as the web
    preview. With frames, saves a looping APNG that holds on the resting
    frame for a couple of seconds between tap-animation plays."""
    date_font = ImageFont.truetype(font_path, 16)
    time_font = ImageFont.truetype(font_path, 32)
    today = date.today()
    date_text = today.strftime("%a %d").upper()

    def compose(avatar: Image.Image) -> Image.Image:
        face = Image.new("RGB", (SCREEN_W, SCREEN_H), (0, 0, 0))
        face.paste(avatar, ((SCREEN_W - avatar.width) // 2, AVATAR_Y))
        draw = ImageDraw.Draw(face)
        draw.text((6, 4), date_text, font=date_font, fill=(255, 255, 255))
        _draw_battery(draw, SCREEN_W - 32, 5, 80, accent)
        draw.text((SCREEN_W // 2, TIME_Y), "10:09", font=time_font, fill=accent, anchor="mt")
        return face

    if not frames:
        compose(Image.open(avatar_path).convert("RGB")).save(output_path, "PNG")
        return

    faces = [compose(f) for f in frames]
    durations = [2500] + [FRAME_MS] * (len(faces) - 1)
    save_apng(faces, output_path, durations, loop=0)


if __name__ == "__main__":
    import sys
    pixelize(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 160)
