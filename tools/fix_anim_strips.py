"""Downscale oversized animated texture strips in Modernity-GTNH.

Certain item textures ship as enormous animated strips, e.g.:
  368x40112  = 109 frames of 368x368   (bee parts, analyzer icons, OC Beekeeper)
  400x40000  = 100 frames of 400x400   (gt.metaitem.01/415, /417)

Minecraft only ever draws item icons at up to 64x64 (16px * max GUI scale),
so each frame is stored far larger than displayed: ~56 MB decoded per texture,
~1.98 GB across all 35 strips (see issue #271).

This script splits each strip into frames, resizes every frame to TARGET x
TARGET (BOX/area resampling), and reassembles a TARGET x (TARGET * frames)
strip in place. Frame count and .mcmeta animations are untouched.

Usage:
  python tools/fix_anim_strips.py                 # dry run (default TARGET=64)
  python tools/fix_anim_strips.py --target 128    # dry run at another size
  python tools/fix_anim_strips.py --target 96 --apply

TARGET is your quality/memory tradeoff, e.g.:
  64  -> ~59 MB total  (-97%)   exactly native max display size
  96  -> ~132 MB total (-93%)
  128 -> ~237 MB total (-88%)   keeps zoomed views near-original
"""
import os
import struct
import sys

from PIL import Image

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")


def png_size(path):
    with open(path, "rb") as fh:
        head = fh.read(26)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", head[16:24])


def block_uniform(im, factor):
    """True if every factor x factor block of the frame is a single color."""
    px = im.load()
    w, h = im.size
    for by in range(0, h, factor):
        for bx in range(0, w, factor):
            c0 = px[bx, by]
            for y in range(by, min(by + factor, h)):
                for x in range(bx, min(bx + factor, w)):
                    if px[x, y] != c0:
                        return False
    return True


def parse_args(argv):
    target = 64
    apply = False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--apply":
            apply = True
        elif a == "--target":
            i += 1
            if i >= len(argv):
                sys.exit("--target needs a number, e.g. --target 128")
            target = int(argv[i])
        elif a in ("-h", "--help"):
            print(__doc__)
            raise SystemExit(0)
        else:
            sys.exit(f"unknown argument: {a}\nusage: fix_anim_strips.py [--target N] [--apply]")
        i += 1
    if not 16 <= target <= 512:
        sys.exit("--target must be between 16 and 512")
    return target, apply


def main():
    target, apply = parse_args(sys.argv[1:])
    dry = not apply
    whales = []
    for dirpath, _dirs, files in os.walk(ROOT):
        for fn in files:
            if not fn.endswith(".png"):
                continue
            p = os.path.join(dirpath, fn)
            size = png_size(p)
            if not size:
                continue
            w, h = size
            if w >= 100 and h >= 1000 and h % w == 0 and h // w >= 2:
                whales.append((p, w, h, h // w))

    print(f"target={target}px  strips={len(whales)}  mode={'APPLY' if apply else 'dry-run'}")
    total_before = total_after = 0
    uniform_ok = 0
    for p, w, h, frames in sorted(whales, key=lambda t: -t[2] * t[1]):
        rel = os.path.relpath(p, ROOT)
        factor = max(1, w // target)
        before = os.path.getsize(p)
        total_before += w * h * 4
        im = Image.open(p).convert("RGBA")
        f0 = im.crop((0, 0, w, w))
        uniform = block_uniform(f0, factor) if w <= 512 else False
        uniform_ok += bool(uniform)
        out = Image.new("RGBA", (target, target * frames))
        for i in range(frames):
            frame = im.crop((0, i * w, w, (i + 1) * w)).resize((target, target), Image.BOX)
            out.paste(frame, (0, i * target))
        total_after += target * target * frames * 4
        mark = "uniform(lossless)" if uniform else "resampled"
        if dry:
            print(f"  {w}x{h} ({frames}f) -> {target}x{target * frames}  [{mark}]  {rel}")
        else:
            out.save(p, "PNG", optimize=True)
            after = os.path.getsize(p)
            print(f"  {w}x{h} -> {target}x{target * frames}  [{mark}]  {before // 1024}KB -> {after // 1024}KB  {rel}")
    print(f"decoded total: {total_before / 1024 / 1024:.0f} MB -> {total_after / 1024 / 1024:.1f} MB")
    print(f"block-uniform frame0: {uniform_ok}/{len(whales)}")
    if dry:
        print("DRY RUN - re-run with --apply to write")


if __name__ == "__main__":
    main()
