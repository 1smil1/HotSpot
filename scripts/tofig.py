#!/usr/bin/env python3

from __future__ import annotations

import argparse
import math
import tempfile
from pathlib import Path


MAXX = 9600
MAXY = 12600
RES = 1200
SKINNY = 3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("-a", dest="occupancy", type=float, default=0.95)
    parser.add_argument("-f", dest="fontsize", type=int, default=10)
    parser.add_argument("-s", dest="nskip", type=int, default=0)
    parser.add_argument("file")
    return parser.parse_args()


def emit_fig_like_from_floorplan(input_path: Path) -> Path:
    temp = tempfile.NamedTemporaryFile("w", delete=False, suffix=".figlike", encoding="utf-8")
    with input_path.open("r", encoding="utf-8") as src, temp as dst:
        dst.write("FIG starts\n")
        for raw_line in src:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) not in (3, 5):
                raise ValueError("wrong floorplan input format")
            if len(parts) == 3:
                continue
            name, width, height, leftx, bottomy = parts
            rightx = float(leftx) + float(width)
            topy = float(bottomy) + float(height)
            dst.write(
                f"{float(leftx):.16f} {float(bottomy):.16f} {float(leftx):.16f} {topy:.16f} "
                f"{rightx:.16f} {topy:.16f} {rightx:.16f} {float(bottomy):.16f} "
                f"{float(leftx):.16f} {float(bottomy):.16f}\n"
            )
            dst.write(f"{name}\n")
        dst.write("FIG ends\n")
    return Path(temp.name)


def main() -> int:
    args = parse_args()
    input_path = Path(args.file)
    if not input_path.is_file():
        raise SystemExit(f"error: file {input_path} could not be opened")

    generated = None
    with input_path.open("r", encoding="utf-8") as handle:
        lines = handle.readlines()

    try:
        fig_start = next(i for i, line in enumerate(lines) if "FIG starts" in line)
    except StopIteration:
        generated = emit_fig_like_from_floorplan(input_path)
        lines = generated.read_text(encoding="utf-8").splitlines(True)
        fig_start = next(i for i, line in enumerate(lines) if "FIG starts" in line)

    data_lines: list[list[float]] = []
    pos = fig_start + 1
    skipped = 0
    while pos < len(lines):
        line = lines[pos].strip()
        pos += 1
        if line == "FIG ends":
            break
        if not line or any(ch.isalpha() or ch == "_" for ch in line):
            continue
        if skipped < args.nskip:
            skipped += 1
            continue
        nums = [float(item) for item in line.split()]
        data_lines.append(nums)

    flat = [value for coords in data_lines for value in coords]
    maxfig = max(flat)
    minfig = min(flat)
    span = maxfig - minfig
    scale = min(MAXX, MAXY) / span * math.sqrt(args.occupancy)
    xorig = (MAXX - span * scale) / 2
    yorig = (MAXY - span * scale) / 2

    print(f"#FIG 3.1\nPortrait\nCenter\nInches\n{RES} 2")

    pos = fig_start + 1
    skipped_lines = 0
    while pos < len(lines):
        line = lines[pos].rstrip("\n")
        pos += 1
        if line == "FIG ends":
            break
        if skipped_lines < args.nskip * 2:
            skipped_lines += 1
            continue
        if not line.strip():
            continue
        coords = [float(item) for item in line.split()]
        coords = [(value - minfig) * scale for value in coords]
        leftx = rightx = coords[0]
        bottomy = topy = coords[1]
        for index in range(2, len(coords)):
            if index % 2:
                bottomy = min(bottomy, coords[index])
                topy = max(topy, coords[index])
            else:
                leftx = min(leftx, coords[index])
                rightx = max(rightx, coords[index])
        fig_coords = []
        for index, value in enumerate(coords):
            if index % 2:
                fig_coords.append(int(MAXY - value - yorig))
            else:
                fig_coords.append(int(value + xorig))
        print(f"2 2 0 1 -1 7 0 0 -1 0.000 0 0 0 0 0 {len(fig_coords) // 2}")
        print("\t" + " ".join(str(item) for item in fig_coords))
        name = lines[pos].strip()
        pos += 1
        xpos = int(xorig + (leftx + rightx) / 2.0)
        ypos = int(MAXY - (bottomy + topy) / 2.0 - yorig)
        angle = 1.5708 if (topy - bottomy) > SKINNY * (rightx - leftx) else 0
        print(f"4 1 -1 0 0 0 {args.fontsize} {angle} 4 -1 -1 {xpos} {ypos} {name}\\001")

    if generated is not None:
        generated.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
