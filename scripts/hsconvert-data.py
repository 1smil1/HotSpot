#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path


def read_names(path: Path) -> list[str]:
    names = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) not in (3, 5):
            raise SystemExit("error: wrong floorplan input format")
        if len(parts) == 5:
            names.append(parts[0])
    return names


def get_chopcount(original: Path, converted: Path) -> dict[str, int]:
    original_names = read_names(original)
    converted_names = read_names(converted)
    chopcount: dict[str, int] = {}
    for original_name in original_names:
        matches = [name for name in converted_names if name.startswith(f"{original_name}_")]
        if matches:
            chopcount[original_name] = len(matches)
    return chopcount


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("-o", dest="original", required=True)
    parser.add_argument("-c", dest="converted", required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-p", dest="power")
    group.add_argument("-t", dest="temp")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    original = Path(args.original)
    converted = Path(args.converted)
    trace = Path(args.power or args.temp)
    for path in (original, converted, trace):
        if not path.is_file():
            raise SystemExit(f"error: file {path} could not be opened for reading")

    chopcount = get_chopcount(original, converted)
    lines = [line.rstrip("\n") for line in trace.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        raise SystemExit("error: empty trace file")
    names = lines[0].split()

    header = []
    for name in names:
        count = chopcount.get(name, 0)
        if count:
            header.extend(f"{name}_{index}" for index in range(count))
        else:
            header.append(name)
    print("\t".join(header))

    is_power = args.power is not None
    for raw_line in lines[1:]:
        if raw_line.lstrip().startswith("#"):
            continue
        values = raw_line.split()
        out = []
        for name, value_s in zip(names, values):
            count = chopcount.get(name, 0)
            value = float(value_s)
            if count:
                if is_power:
                    value /= count
                out.extend(str(value) for _ in range(count))
            else:
                out.append(str(value))
        print("\t".join(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
