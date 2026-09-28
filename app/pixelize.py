import colorsys

from PIL import Image

# Grid resolution the art is designed at, before blocky upscale.
RAW_PHOTO_GRID = 40   # aggressive: raw photos have far more color/detail noise
                      # than a hardware sprite should, so crush it hard
STYLIZED_GRID = 64    # gentle: Kling's output is already pixel-art-ish, this
                      # just cleans up JPEG/AI shading noise into flat blocks

RAW_PHOTO_COLORS = 32  # forces a retro-limited palette for messy photos;
                       # Pebble's own PNG->bitmap step further snaps to its
                       # fixed 64-color hardware palette on build either way


def pixelize(input_path: str, output_path: str, box_size: int, source_is_stylized: bool = False) -> None:
    """Downsample to a small grid, then upscale with nearest-neighbor so the
    result reads as blocky pixel art instead of a smoothed-down photo.

    source_is_stylized=True skips the harsh color quantization (for images
    that already came back from Kling as pixel art — re-quantizing an
    already-limited palette just muddies it) and uses a finer grid so more
    of Kling's detail survives the blocky-ification.
    """
    img = Image.open(input_path).convert("RGB")

    side = min(img.size)
    left = (img.width - side) // 2
    top = (img.height - side) // 2
    img = img.crop((left, top, left + side, top + side))

    grid = STYLIZED_GRID if source_is_stylized else RAW_PHOTO_GRID
    small = img.resize((grid, grid), Image.BOX)

    if source_is_stylized:
        blocky = small.resize((box_size, box_size), Image.NEAREST)
    else:
        quantized = small.quantize(colors=RAW_PHOTO_COLORS, method=Image.MEDIANCUT)
        blocky = quantized.resize((box_size, box_size), Image.NEAREST)

    blocky.convert("RGB").save(output_path, "PNG")


def extract_accent_color(image_path: str) -> tuple[int, int, int]:
    """Pick a vibrant accent color from the image for the watch's time text.
    A plain average tends toward muddy gray/brown, so instead: quantize down
    to a handful of colors and pick the most saturated one in a sane
    brightness range, weighted by how much of the image it covers. Falls
    back to white if nothing qualifies (e.g. a near-grayscale image)."""
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
    return candidates[0][2]


if __name__ == "__main__":
    import sys
    pixelize(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 160)
