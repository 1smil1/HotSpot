#!/usr/bin/env python3

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("-a", dest="occupancy", type=float, default=0.95)
    parser.add_argument("-f", dest="fontsize", type=int, default=10)
    parser.add_argument("-s", dest="nskip", type=int, default=0)
    parser.add_argument("file")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    lcf_path = Path(args.file)
    if not lcf_path.is_file():
        raise SystemExit(f"error: file {lcf_path} could not be opened")

    script_dir = Path(__file__).resolve().parent
    lcf_dir = lcf_path.resolve().parent
    floorplans: list[Path] = []
    for raw_line in lcf_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip().replace("\r", "")
        if not line or line.startswith("#") or not line.endswith(".flp"):
            continue
        floorplans.append(lcf_dir / line)

    for floorplan in floorplans:
        output_path = floorplan.with_suffix(".fig")
        print(output_path.name)
        result = subprocess.run(
            [
                sys.executable,
                str(script_dir / "tofig.py"),
                "-a", str(args.occupancy),
                "-f", str(args.fontsize),
                "-s", str(args.nskip),
                str(floorplan),
            ],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(lcf_dir),
        )
        if result.returncode != 0:
            sys.stderr.write(result.stderr)
            return result.returncode
        output_path.write_text(result.stdout, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
