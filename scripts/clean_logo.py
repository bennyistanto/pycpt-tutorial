"""Remove a baked-in transparency checkerboard from the tutorial logos and crop them.

The supplied logos draw a grey/white (or black/grey) checkerboard into the pixels
instead of using real transparency. This script makes those checkerboard regions
transparent, paints the whiteboard's surface one solid colour (it carries the same
checkerboard), crops to the drawing and resizes.

    python scripts/clean_logo.py temp/logo-originals/logo-light.png docs/assets/logo/logo-light.png --mode light
    python scripts/clean_logo.py temp/logo-originals/logo-dark.png docs/assets/logo/logo-dark.png --mode dark
"""
import argparse
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage


def background_like(rgb, mode, spread_limit=12):
    low, high = rgb.min(axis=2), rgb.max(axis=2)
    neutral = (high - low) <= spread_limit
    if mode == "light":
        return neutral & (low >= 228)
    return neutral & (high <= 28)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--mode", choices=("light", "dark"), required=True)
    parser.add_argument("--keep-box", type=int, nargs=4, default=(660, 565, 1740, 1330),
                        metavar=("X0", "Y0", "X1", "Y1"),
                        help="background-like regions entirely inside this box (the whiteboard) are kept")
    parser.add_argument("--board-fill", type=int, nargs=3, metavar=("R", "G", "B"),
                        help="solid colour for the kept board surface (default: white for light, charcoal for dark)")
    parser.add_argument("--margin", type=int, default=24, help="pixels kept around the drawing")
    parser.add_argument("--width", type=int, default=1000, help="output width in pixels")
    args = parser.parse_args()

    image = Image.open(args.source).convert("RGBA")
    rgb = np.asarray(image)[..., :3].astype(int)
    candidate = background_like(rgb, args.mode)

    labels, count = ndimage.label(candidate)
    x0, y0, x1, y1 = args.keep_box
    remove = np.zeros_like(candidate)
    board = np.zeros_like(candidate)
    kept = 0
    for index, region in enumerate(ndimage.find_objects(labels), start=1):
        rows, cols = region
        inside_board = rows.start >= y0 and rows.stop <= y1 and cols.start >= x0 and cols.stop <= x1
        if inside_board:
            board[region] |= labels[region] == index
            kept += 1
        else:
            remove[region] |= labels[region] == index

    fill = args.board_fill or ((255, 255, 255) if args.mode == "light" else (24, 24, 26))
    rgb = rgb.copy()
    rgb[board] = fill

    alpha = np.where(remove, 0.0, 255.0)
    alpha = ndimage.gaussian_filter(alpha, sigma=0.7)
    alpha[~remove & (ndimage.binary_erosion(~remove, iterations=2))] = 255
    rgba = np.dstack([rgb, alpha.clip(0, 255)]).astype(np.uint8)

    ys, xs = np.nonzero(rgba[..., 3] > 16)
    top, bottom = max(ys.min() - args.margin, 0), min(ys.max() + args.margin + 1, rgba.shape[0])
    left, right = max(xs.min() - args.margin, 0), min(xs.max() + args.margin + 1, rgba.shape[1])
    cropped = Image.fromarray(rgba[top:bottom, left:right], "RGBA")
    height = round(cropped.height * args.width / cropped.width)
    cropped = cropped.resize((args.width, height), Image.LANCZOS)

    args.destination.parent.mkdir(parents=True, exist_ok=True)
    cropped.save(args.destination, optimize=True)
    print(f"{args.source.name}: {count} background-like regions, {kept} kept inside the board; "
          f"crop {right - left}x{bottom - top} from {image.width}x{image.height}; "
          f"saved {args.width}x{height}, {args.destination.stat().st_size / 1000:.0f} kB")


if __name__ == "__main__":
    main()
