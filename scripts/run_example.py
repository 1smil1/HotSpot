#!/usr/bin/env python3

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
HOTSPOT = REPO_ROOT / "hotspot.exe"
HOTFLOORPLAN = REPO_ROOT / "hotfloorplan.exe"
PYTHON = Path(os.environ.get("HOTSPOT_PYTHON", sys.executable))
PERL = shutil.which("perl")


def assert_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")


def test_python_module(module_name: str) -> bool:
    result = subprocess.run(
        [str(PYTHON), "-c", f"import {module_name}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def reset_outputs(example_dir: Path, init_patterns: list[str] | None = None) -> None:
    init_patterns = init_patterns or ["*.init"]
    for pattern in init_patterns:
        for path in example_dir.glob(pattern):
            if path.is_file():
                path.unlink()

    outputs_dir = example_dir / "outputs"
    outputs_dir.mkdir(exist_ok=True)
    for path in outputs_dir.iterdir():
        if path.is_file():
            path.unlink()


def run_checked(command: list[str], cwd: Path) -> None:
    result = subprocess.run(command, cwd=str(cwd), check=False)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {result.returncode}: {' '.join(command)}")


def run_example1() -> None:
    example_dir = REPO_ROOT / "examples" / "example1"
    reset_outputs(example_dir, ["gcc.init"])
    run_checked(
        [
            str(HOTSPOT),
            "-c", "example.config",
            "-f", "ev6.flp",
            "-p", "gcc.ptrace",
            "-materials_file", "example.materials",
            "-model_type", "block",
            "-steady_file", r"outputs\gcc.steady",
            "-o", r"outputs\gcc.ttrace",
        ],
        example_dir,
    )
    shutil.copyfile(example_dir / "outputs" / "gcc.steady", example_dir / "gcc.init")
    run_checked(
        [
            str(HOTSPOT),
            "-c", "example.config",
            "-init_file", "gcc.init",
            "-f", "ev6.flp",
            "-p", "gcc.ptrace",
            "-materials_file", "example.materials",
            "-model_type", "block",
            "-o", r"outputs\gcc.ttrace",
        ],
        example_dir,
    )


def run_example2() -> None:
    example_dir = REPO_ROOT / "examples" / "example2"
    reset_outputs(example_dir, ["gcc.init"])
    run_checked(
        [
            str(HOTSPOT),
            "-c", "example.config",
            "-f", "ev6.flp",
            "-p", "gcc.ptrace",
            "-materials_file", "example.materials",
            "-model_type", "grid",
            "-steady_file", r"outputs\gcc.steady",
            "-grid_steady_file", r"outputs\gcc.grid.steady",
        ],
        example_dir,
    )
    shutil.copyfile(example_dir / "outputs" / "gcc.steady", example_dir / "gcc.init")
    run_checked(
        [
            str(HOTSPOT),
            "-c", "example.config",
            "-init_file", "gcc.init",
            "-f", "ev6.flp",
            "-p", "gcc.ptrace",
            "-materials_file", "example.materials",
            "-model_type", "grid",
            "-o", r"outputs\gcc.ttrace",
            "-grid_transient_file", r"outputs\gcc.grid.ttrace",
        ],
        example_dir,
    )
    run_checked([str(PYTHON), str(REPO_ROOT / "scripts" / "split_grid_steady.py"), r"outputs\gcc.grid.steady", "4", "64", "64"], example_dir)
    if test_python_module("matplotlib") and test_python_module("numpy"):
        run_checked(
            [str(PYTHON), str(REPO_ROOT / "scripts" / "grid_thermal_map.py"), "ev6.flp", r"outputs\gcc_layer0.grid.steady", r"outputs\gcc.png"],
            example_dir,
        )
        run_checked(
            [str(PYTHON), str(REPO_ROOT / "scripts" / "grid_thermal_map.py"), "ev6.flp", r"outputs\gcc_layer0.grid.steady", r"outputs\gcc.svg"],
            example_dir,
        )
    else:
        print("WARNING: Skipping Python heat maps for example2 because matplotlib/numpy is unavailable.")


def run_example3() -> None:
    example_dir = REPO_ROOT / "examples" / "example3"
    reset_outputs(example_dir)
    run_checked(
        [
            str(HOTSPOT),
            "-c", "example.config",
            "-p", "example.ptrace",
            "-grid_layer_file", "example.lcf",
            "-materials_file", "example.materials",
            "-model_type", "grid",
            "-detailed_3D", "on",
            "-steady_file", r"outputs\example.steady",
            "-grid_steady_file", r"outputs\example.grid.steady",
        ],
        example_dir,
    )
    shutil.copyfile(example_dir / "outputs" / "example.steady", example_dir / "example.init")
    run_checked(
        [
            str(HOTSPOT),
            "-c", "example.config",
            "-p", "example.ptrace",
            "-grid_layer_file", "example.lcf",
            "-materials_file", "example.materials",
            "-model_type", "grid",
            "-detailed_3D", "on",
            "-o", r"outputs\example.ttrace",
            "-grid_transient_file", r"outputs\example.grid.ttrace",
        ],
        example_dir,
    )
    run_checked([str(PYTHON), str(REPO_ROOT / "scripts" / "split_grid_steady.py"), r"outputs\example.grid.steady", "6", "64", "64"], example_dir)
    if test_python_module("matplotlib") and test_python_module("numpy"):
        run_checked(
            [str(PYTHON), str(REPO_ROOT / "scripts" / "grid_thermal_map.py"), "floorplan2.flp", r"outputs\example_layer2.grid.steady", "64", "64", r"outputs\layer2.png"],
            example_dir,
        )
        run_checked(
            [str(PYTHON), str(REPO_ROOT / "scripts" / "grid_thermal_map.py"), "floorplan2.flp", r"outputs\example_layer2.grid.steady", "64", "64", r"outputs\layer2.svg"],
            example_dir,
        )
    else:
        print("WARNING: Skipping Python heat maps for example3 because matplotlib/numpy is unavailable.")


def run_example4() -> None:
    example_dir = REPO_ROOT / "examples" / "example4"
    reset_outputs(example_dir)
    run_checked(
        [
            str(HOTSPOT),
            "-c", "example.config",
            "-p", "ev6_3D.ptrace",
            "-grid_layer_file", "ev6_3D.lcf",
            "-model_type", "grid",
            "-detailed_3D", "on",
            "-grid_steady_file", r"outputs\example.grid.steady",
            "-steady_file", r"outputs\example.steady",
        ],
        example_dir,
    )
    shutil.copyfile(example_dir / "outputs" / "example.steady", example_dir / "example.init")
    run_checked(
        [
            str(HOTSPOT),
            "-c", "example.config",
            "-p", "ev6_3D.ptrace",
            "-grid_layer_file", "ev6_3D.lcf",
            "-init_file", "example.init",
            "-model_type", "grid",
            "-detailed_3D", "on",
            "-o", r"outputs\example.transient",
            "-grid_transient_file", r"outputs\example.grid.ttrace",
        ],
        example_dir,
    )


def run_example5() -> None:
    example_dir = REPO_ROOT / "examples" / "example5"
    reset_outputs(example_dir)
    try:
        run_checked(
            [
                str(HOTSPOT),
                "-c", "example.config",
                "-p", "example.ptrace",
                "-materials_file", "example.materials",
                "-grid_layer_file", "example.lcf",
                "-model_type", "grid",
                "-detailed_3D", "on",
                "-use_microchannels", "1",
                "-grid_steady_file", r"outputs\example.grid.steady",
                "-steady_file", r"outputs\example.steady",
            ],
            example_dir,
        )
        shutil.copyfile(example_dir / "outputs" / "example.steady", example_dir / "example.init")
        run_checked(
            [
                str(HOTSPOT),
                "-c", "example.config",
                "-p", "example.ptrace",
                "-materials_file", "example.materials",
                "-grid_layer_file", "example.lcf",
                "-init_file", "example.init",
                "-model_type", "grid",
                "-detailed_3D", "on",
                "-use_microchannels", "1",
                "-o", r"outputs\example.transient",
                "-grid_transient_file", r"outputs\example.grid.ttrace",
            ],
            example_dir,
        )
    except RuntimeError as exc:
        raise RuntimeError(
            "Example5 requires HotSpot built with SuperLU support. "
            "Rebuild with SUPERLU=1 after installing SuperLU/BLAS. "
            f"Original error: {exc}"
        ) from exc


def run_example6() -> None:
    example_dir = REPO_ROOT / "examples" / "example6"
    output_path = example_dir / "output.flp"
    if output_path.exists():
        output_path.unlink()
    run_checked(
        [str(HOTFLOORPLAN), "-c", "example.config", "-f", "ev6.desc", "-p", "avg.p", "-o", "output.flp"],
        example_dir,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("example", nargs="?", default="1", choices=["1", "2", "3", "4", "5", "6", "all"])
    args = parser.parse_args()

    assert_file(HOTSPOT)
    assert_file(HOTFLOORPLAN)

    runners = {
        "1": run_example1,
        "2": run_example2,
        "3": run_example3,
        "4": run_example4,
        "5": run_example5,
        "6": run_example6,
    }
    items = ["1", "2", "3", "4", "5", "6"] if args.example == "all" else [args.example]
    for item in items:
        print(f"Running example{item}...")
        runners[item]()
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
