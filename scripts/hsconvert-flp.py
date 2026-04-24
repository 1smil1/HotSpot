#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("-a", dest="threshold", type=float, default=1.0)
    parser.add_argument("file")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.threshold < 1.0:
        raise SystemExit("error: aspect ratio should be >= 1")
    input_path = Path(args.file)
    if not input_path.is_file():
        raise SystemExit(f"error: file {input_path} could not be opened for reading")

    chopcount: dict[str, int] = {}
    for raw_line in input_path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            print(raw_line)
            continue
        parts = raw_line.split()
        if len(parts) not in (3, 5):
            raise SystemExit("error: wrong floorplan input format")
        if len(parts) == 5:
            name, width_s, height_s, leftx_s, bottomy_s = parts
            width = float(width_s)
            height = float(height_s)
            leftx = float(leftx_s)
            bottomy = float(bottomy_s)
            aspect = height / width
            vertical = True
            if aspect < 1:
                aspect = 1.0 / aspect
                vertical = False
            if aspect > args.threshold:
                factor = int(aspect / args.threshold + 0.5)
                if factor <= 1:
                    print("\t".join(parts))
                    continue
                chopcount[name] = factor
                if vertical:
                    height /= factor
                else:
                    width /= factor
                for index in range(factor):
                    print(f"{name}_{index}\t{width:.6f}\t{height:.6f}\t{leftx:.6f}\t{bottomy:.6f}")
                    if vertical:
                        bottomy += height
                    else:
                        leftx += width
            else:
                print("\t".join(parts))
        else:
            name1, name2, density = parts
            count1 = chopcount.get(name1, 0)
            count2 = chopcount.get(name2, 0)
            if count1 and count2:
                for i in range(count1):
                    for j in range(count2):
                        print(f"{name1}_{i}\t{name2}_{j}\t{float(density):.3f}")
            elif count1:
                for i in range(count1):
                    print(f"{name1}_{i}\t{name2}\t{float(density):.3f}")
            elif count2:
                for i in range(count2):
                    print(f"{name1}\t{name2}_{i}\t{float(density):.3f}")
            else:
                print("\t".join(parts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
