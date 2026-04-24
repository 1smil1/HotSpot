#!/usr/bin/env python3

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

USAGE = """
usage: grid_thermal_map.py <flp_file> <grid_temp_file> <filename>.png|svg (or)
       grid_thermal_map.py <flp_file> <grid_temp_file> <rows> <cols> <filename>.png|svg (or)
       grid_thermal_map.py <flp_file> <grid_temp_file> <rows> <cols> <min> <max> <filename>.png|svg
"""

PALETTE = [
    "255,0,0", "255,51,0", "255,102,0", "255,153,0", "255,204,0",
    "255,255,0", "204,255,0", "153,255,0", "102,255,0", "51,255,0",
    "0,255,0", "0,255,51", "0,255,102", "0,255,153", "0,255,204",
    "0,255,255", "0,204,255", "0,153,255", "0,102,255", "0,51,255",
    "0,0,255",
]


def parse_args(argv: list[str]) -> tuple[Path, Path, int, int, float | None, float | None, Path]:
    if len(argv) == 4:
        rows, cols = 64, 64
        min_temp = max_temp = None
        return Path(argv[1]), Path(argv[2]), rows, cols, min_temp, max_temp, Path(argv[3])
    if len(argv) == 6:
        return Path(argv[1]), Path(argv[2]), int(argv[3]), int(argv[4]), None, None, Path(argv[5])
    if len(argv) == 8:
        return Path(argv[1]), Path(argv[2]), int(argv[3]), int(argv[4]), float(argv[5]), float(argv[6]), Path(argv[7])
    print(USAGE)
    raise SystemExit(1)


def read_floorplan(path: Path) -> tuple[list[tuple[str, float, float, float, float]], float, float]:
    blocks: list[tuple[str, float, float, float, float]] = []
    total_width = 0.0
    total_height = 0.0
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 5:
                continue
            name = parts[0]
            width = float(parts[1])
            height = float(parts[2])
            x = float(parts[3])
            y = float(parts[4])
            blocks.append((name, width, height, x, y))
            total_width = max(total_width, x + width)
            total_height = max(total_height, y + height)
    return blocks, total_width, total_height


def read_temperatures(path: Path, rows: int, cols: int) -> np.ndarray:
    temps = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            parts = line.split()
            if len(parts) >= 2:
                temps.append(float(parts[1]))
    return np.reshape(np.array(temps, dtype=float), (rows, cols))


def color_for_temp(value: float, min_temp: float, max_temp: float) -> str:
    if max_temp <= min_temp:
        index = 0
    else:
        ratio = (max_temp - value) / (max_temp - min_temp)
        index = int(ratio * (len(PALETTE) - 1))
        index = max(0, min(index, len(PALETTE) - 1))
    return PALETTE[index]


def write_svg(
    output_path: Path,
    blocks: list[tuple[str, float, float, float, float]],
    temps: np.ndarray,
    total_width: float,
    total_height: float,
    min_temp: float,
    max_temp: float,
) -> None:
    zoom = 1_000_000.0
    num_levels = len(PALETTE)
    width = total_width * zoom
    height = total_height * zoom
    grid_h = height / temps.shape[0]
    grid_w = width / temps.shape[1]
    x_bound = width * 1.2
    txt_offset = 100.0
    smallest_shown = 10_000.0

    lines = [
        '<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.0//EN"',
        '    "http://www.w3.org/TR/2001/REC-SVG-20010904/DTD/svg10.dtd">',
        f'<svg width="900px" height="500px" viewBox="0 0 {x_bound:.0f} {height:.0f}">',
        "<title>Sample Temperature Map For HotSpot Grid Model</title>",
    ]

    lines.append('<g id="thermal_map" style="stroke: none;">')
    for row in range(temps.shape[0]):
        for col in range(temps.shape[1]):
            x = col * grid_w
            y = row * grid_h
            color = color_for_temp(float(temps[row, col]), min_temp, max_temp)
            lines.append(
                f'<rect x="{x:.0f}" y="{y:.0f}" width="{grid_w:.0f}" height="{grid_h:.0f}" '
                f'style="fill:rgb({color})" />'
            )
    lines.append("</g>")

    lines.append('<g id="floorplan" style="stroke:black; fill:none;">')
    for name, block_w, block_h, x, y in blocks:
        rect_x = x * zoom
        rect_y = height - (y * zoom) - (block_h * zoom)
        rect_w = block_w * zoom
        rect_h = block_h * zoom
        if rect_w <= width / smallest_shown or rect_h <= height / smallest_shown:
            continue
        lines.append(
            f'<rect x="{rect_x:.0f}" y="{rect_y:.0f}" width="{rect_w:.0f}" height="{rect_h:.0f}" '
            'style="fill:none;stroke:black;stroke-width:30" />'
        )
        lines.append(
            f'<text x="{rect_x + txt_offset:.0f}" y="{rect_y + 2 * txt_offset:.0f}" '
            'fill="black" text-anchor="start" style="font-size:180">'
            f" {name} </text>"
        )
    lines.append("</g>")

    scale_x = width * 1.1
    scale_label_x = width * 1.05
    scale_y = height * 0.05
    scale_w = width * 0.05
    scale_h = height * 0.025
    for index, color in enumerate(PALETTE):
        lines.append(
            f'<rect x="{scale_x:.0f}" y="{scale_y:.0f}" width="{scale_w:.0f}" height="{scale_h:.0f}" '
            f'style="fill:rgb({color});stroke:none" />'
        )
        if index % 3 == 0:
            value = (max_temp - min_temp) * (1 - index / (num_levels - 1)) + min_temp
            lines.append(
                f'<text x="{scale_label_x:.0f}" y="{scale_y + scale_h * 0.5:.0f}" '
                'fill="black" text-anchor="start" style="font-size:250">'
                f" {value:.2f} </text>"
            )
        scale_y += scale_h
    lines.append(
        f'<text x="{scale_label_x:.0f}" y="{scale_y:.0f}" fill="black" text-anchor="start" '
        f'style="font-size:250"> {min_temp:.2f} </text>'
    )
    lines.append("</svg>")
    output_path.write_text("\n".join(lines), encoding="utf-8")


def write_png(
    output_path: Path,
    blocks: list[tuple[str, float, float, float, float]],
    temps: np.ndarray,
    total_width: float,
    total_height: float,
    min_temp: float | None,
    max_temp: float | None,
) -> None:
    import matplotlib.pyplot as plt

    fig, axs = plt.subplots(1)
    for name, width, height, x, y in blocks:
        rectangle = plt.Rectangle((x, y), width, height, fc="none", ec="black")
        axs.add_patch(rectangle)
        plt.text(x, y, name)

    im = axs.imshow(temps, cmap="hot_r", extent=(0, total_width, 0, total_height))
    if min_temp is None or max_temp is None:
        im.set_clim(float(np.min(temps)), float(np.max(temps)))
    else:
        im.set_clim(min_temp, max_temp)
    fig.colorbar(im, ax=axs)
    axs.set_title(f"Heat Map\nMaximum Temperature = {np.max(temps)}")
    axs.set_xticks([n for n in np.linspace(0, total_width, 5)])
    axs.set_xticklabels([n * (10 ** 3) for n in np.linspace(0, total_width, 5)])
    axs.set_xlabel("Horizontal Position (mm)")
    axs.set_yticks([n for n in np.linspace(0, total_height, 5)])
    axs.set_yticklabels([n * (10 ** 3) for n in np.linspace(0, total_height, 5)])
    axs.set_ylabel("Vertical Position (mm)")
    plt.axis("scaled")
    plt.savefig(output_path)


def main(argv: list[str]) -> int:
    flp_path, temps_path, rows, cols, min_temp, max_temp, output_path = parse_args(argv)
    blocks, total_width, total_height = read_floorplan(flp_path)
    temps = read_temperatures(temps_path, rows, cols)
    resolved_min = float(np.min(temps)) if min_temp is None else min_temp
    resolved_max = float(np.max(temps)) if max_temp is None else max_temp
    suffix = output_path.suffix.lower()
    if suffix == ".svg":
        write_svg(output_path, blocks, temps, total_width, total_height, resolved_min, resolved_max)
    elif suffix == ".png":
        write_png(output_path, blocks, temps, total_width, total_height, min_temp, max_temp)
    else:
        print("output filename must end with .png or .svg")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
