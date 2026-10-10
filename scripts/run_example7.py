#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


REPO_ROOT = Path(__file__).resolve().parent.parent
HOTSPOT = REPO_ROOT / ("hotspot.exe" if os.name == "nt" else "hotspot")
DEFAULT_EXAMPLE_DIR = REPO_ROOT / "examples" / "example7"
DEFAULT_CONFIG_NAME = "example7.config"
DEFAULT_FLP_NAME = "example7.flp"
DEFAULT_PTRACE_NAME = "example7.ptrace"
DEFAULT_INIT_NAME = "example7.init"
DEFAULT_OUTPUT_DIRNAME = "outputs"
MSYS_UCRT_BIN = Path(r"C:\msys64\ucrt64\bin")
CHIPLET_NAME_RE = re.compile(r"^chiplet[_-]?(\d+)$", re.IGNORECASE)


def assert_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")


def load_json(path: Path) -> Dict[str, Any]:
    assert_file(path)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def ensure_runtime_path() -> Dict[str, str]:
    env = os.environ.copy()
    path_entries = env.get("PATH", "").split(os.pathsep) if env.get("PATH") else []
    if MSYS_UCRT_BIN.exists():
        msys_str = str(MSYS_UCRT_BIN)
        if msys_str not in path_entries:
            env["PATH"] = msys_str + os.pathsep + env.get("PATH", "")
    return env


def reset_outputs(example_dir: Path) -> None:
    outputs_dir = example_dir / DEFAULT_OUTPUT_DIRNAME
    outputs_dir.mkdir(parents=True, exist_ok=True)
    for path in outputs_dir.iterdir():
        if path.is_file():
            path.unlink()
    init_path = example_dir / DEFAULT_INIT_NAME
    if init_path.exists():
        init_path.unlink()


def run_checked(command: List[str], cwd: Path, env: Dict[str, str]) -> None:
    result = subprocess.run(command, cwd=str(cwd), env=env, check=False, capture_output=True, text=True)
    log = cwd / DEFAULT_OUTPUT_DIRNAME / 'hotspot.log'
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open('a', encoding='utf-8') as stream:
        stream.write(' '.join(command) + '\n' + result.stdout + '\n' + result.stderr + '\n')
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}: {' '.join(command)}\n{result.stderr}\nSee {log}"
        )


def to_float(value: Any, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"Field '{field_name}' must be numeric, got boolean")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Field '{field_name}' must be numeric, got {value!r}") from exc
    if math.isnan(numeric) or math.isinf(numeric):
        raise ValueError(f"Field '{field_name}' must be finite, got {value!r}")
    return numeric


def to_int(value: Any, field_name: str) -> int:
    try:
        number = to_float(value, field_name)
        if not number.is_integer():
            raise ValueError(f'{field_name} must be an integer')
        return int(number)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Field '{field_name}' must be an integer, got {value!r}") from exc


def infer_chiplet_id_from_name(name: str) -> Optional[int]:
    match = CHIPLET_NAME_RE.match(name.strip())
    if not match:
        return None
    return int(match.group(1))


def rectangles_overlap(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    a_left = a["x_m"]
    a_right = a["x_m"] + a["width_m"]
    a_bottom = a["y_m"]
    a_top = a["y_m"] + a["height_m"]
    b_left = b["x_m"]
    b_right = b["x_m"] + b["width_m"]
    b_bottom = b["y_m"]
    b_top = b["y_m"] + b["height_m"]
    # ThermalManager quantizes geometry to 1 pm; shared edges may differ by float roundoff.
    return (
        min(a_right, b_right) - max(a_left, b_left) > 1e-12
        and min(a_top, b_top) - max(a_bottom, b_bottom) > 1e-12
    )


def normalize_blocks(blocks_raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not blocks_raw:
        raise ValueError("Geometry must contain at least one block")

    seen_names = set()
    blocks: List[Dict[str, Any]] = []
    for index, raw in enumerate(blocks_raw):
        if not isinstance(raw, dict):
            raise ValueError(f"Block at index {index} must be an object")

        chiplet_id = raw['chiplet_id']
        if chiplet_id is None:
            raise ValueError(
                f"Block at index {index} is missing required field 'chiplet_id'"
            )
        chiplet_id = to_int(chiplet_id, "chiplet_id")

        name = raw['name']
        if not isinstance(name, str) or not name or chiplet_id < 0:
            raise ValueError('Geometry requires a nonempty name and nonnegative chiplet_id')
        width_m = to_float(raw['width_m'], 'width_m')
        height_m = to_float(raw['height_m'], 'height_m')
        x_m = to_float(raw['x_m'], 'x_m')
        y_m = to_float(raw['y_m'], 'y_m')

        if width_m <= 0 or height_m <= 0:
            raise ValueError(
                f"Block '{name}' must have positive width/height, got "
                f"width_m={width_m}, height_m={height_m}"
            )
        if name in seen_names:
            raise ValueError(f"Duplicate block name: {name}")
        seen_names.add(name)

        blocks.append(
            {
                "name": name,
                "chiplet_id": chiplet_id,
                "width_m": width_m,
                "height_m": height_m,
                "x_m": x_m,
                "y_m": y_m,
            }
        )

    for i in range(len(blocks)):
        for j in range(i + 1, len(blocks)):
            if rectangles_overlap(blocks[i], blocks[j]):
                raise ValueError(
                    f"Blocks overlap: {blocks[i]['name']} and {blocks[j]['name']}"
                )
    return blocks


def load_geometry_blocks(path: Path) -> List[Dict[str, Any]]:
    data = load_json(path)
    blocks_raw = data['blocks']
    if not isinstance(blocks_raw, list):
        raise ValueError(f"Geometry JSON {path} must contain a list field 'blocks'")
    return normalize_blocks(blocks_raw)


def write_floorplan(path: Path, blocks: List[Dict[str, Any]]) -> None:
    lines = [
        f"{block['name']}\t{block['width_m']:.12g}\t{block['height_m']:.12g}\t"
        f"{block['x_m']:.12g}\t{block['y_m']:.12g}"
        for block in blocks
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_floorplan(path: Path) -> List[Dict[str, Any]]:
    assert_file(path)
    blocks: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            parts = stripped.split()
            if len(parts) < 5:
                raise ValueError(f"Invalid floorplan row at {path}:{lineno}: {stripped}")
            name = parts[0]
            chiplet_id = infer_chiplet_id_from_name(name)
            if chiplet_id is None:
                raise ValueError(
                    f"Example7 v1 requires floorplan names like chiplet0/chiplet_0; "
                    f"cannot infer chiplet_id from '{name}' in {path}:{lineno}"
                )
            blocks.append(
                {
                    "name": name,
                    "chiplet_id": chiplet_id,
                    "width_m": to_float(parts[1], "width_m"),
                    "height_m": to_float(parts[2], "height_m"),
                    "x_m": to_float(parts[3], "x_m"),
                    "y_m": to_float(parts[4], "y_m"),
                }
            )
    return normalize_blocks(blocks)


def validate_timeseries(data: Dict[str, Any], legacy_time_axis: bool = False) -> Dict[int, List[Dict[str, Any]]]:
    chiplets_raw = data['chiplets']
    if not isinstance(chiplets_raw, list):
        raise ValueError("chiplet_power_timeseries.json must contain list field 'chiplets'")

    samples_by_chiplet: Dict[int, List[Dict[str, Any]]] = {}
    expected_steps: Optional[int] = None
    for chiplet in chiplets_raw:
        if not isinstance(chiplet, dict):
            raise ValueError("Each chiplet entry must be an object")
        chiplet_id = to_int(chiplet['chiplet_id'], 'chiplet_id')
        if chiplet_id < 0 or chiplet_id in samples_by_chiplet:
            raise ValueError('Invalid/duplicate timeseries chiplet_id')
        samples = chiplet['samples']
        if not isinstance(samples, list):
            raise ValueError(f"Chiplet {chiplet_id} must contain list field 'samples'")
        if expected_steps is None:
            expected_steps = len(samples)
        elif len(samples) != expected_steps:
            raise ValueError(
                f"Inconsistent sample count across chiplets: chiplet {chiplet_id} has "
                f"{len(samples)}, expected {expected_steps}"
            )
        for sample in samples:
            if not isinstance(sample, dict):
                raise ValueError(f"Chiplet {chiplet_id} has non-object sample entry")
            start = to_float(sample['start_us'], 'start_us')
            end = to_float(sample['end_us'], 'end_us')
            duration = to_float(sample['duration_us'], 'duration_us')
            power = to_float(sample['total_power_uW'], 'total_power_uW')
            if start < 0 or end <= start or power < 0 or not math.isclose(end-start, duration, rel_tol=1e-9, abs_tol=1e-12):
                raise ValueError('Invalid power sample bounds/power')
            if not legacy_time_axis and not math.isclose(duration, data['step_size_us'], rel_tol=1e-9, abs_tol=1e-12):
                raise ValueError('HotSpot power samples must be uniform in duration')
        samples_by_chiplet[chiplet_id] = samples
    return samples_by_chiplet


def build_ptrace_rows(
    blocks: List[Dict[str, Any]],
    power_timeseries: Dict[str, Any],
    legacy_time_axis: bool = False,
) -> tuple[List[str], List[List[float]], float]:
    step_size_us = to_float(power_timeseries['step_size_us'], 'step_size_us')
    if step_size_us <= 0:
        raise ValueError(f"step_size_us must be > 0, got {step_size_us}")

    samples_by_chiplet = validate_timeseries(power_timeseries, legacy_time_axis)
    num_steps = to_int(power_timeseries['num_steps'], 'num_steps')
    if num_steps <= 0 or any(len(samples) != num_steps for samples in samples_by_chiplet.values()):
        raise ValueError('Power timeseries num_steps must match nonempty sample arrays')
    ids = [b['chiplet_id'] for b in blocks]
    if len(set(ids)) != len(ids) or set(ids) != set(samples_by_chiplet):
        raise ValueError('Geometry/timeseries chiplet inventory must match exactly')
    if not legacy_time_axis:
        start = to_float(power_timeseries['global_start_us'], 'global_start_us')
        end = to_float(power_timeseries['global_end_us'], 'global_end_us')
        if start < 0 or end <= start or not math.isclose(end-start, num_steps*step_size_us, rel_tol=1e-9, abs_tol=1e-12):
            raise ValueError('Declared global duration must equal num_steps times step_size_us')
        for chiplet_id, samples in samples_by_chiplet.items():
            for index, sample in enumerate(samples):
                if not math.isclose(sample['start_us'], start+index*step_size_us, rel_tol=1e-9, abs_tol=1e-12) or not math.isclose(sample['end_us'], start+(index+1)*step_size_us, rel_tol=1e-9, abs_tol=1e-12):
                    raise ValueError(f'Chiplet {chiplet_id} sample {index} timestamps must use the identical continuous global time axis')

    header = [block["name"] for block in blocks]
    rows: List[List[float]] = []

    for step_index in range(num_steps):
        row: List[float] = []
        for block in blocks:
            chiplet_id = block["chiplet_id"]
            chiplet_samples = samples_by_chiplet.get(chiplet_id)
            if chiplet_samples is None:
                raise ValueError(
                    f"No timeseries samples found for chiplet_id={chiplet_id} "
                    f"(block name '{block['name']}')"
                )
            if step_index >= len(chiplet_samples):
                raise ValueError(
                    f"Chiplet {chiplet_id} is missing sample index {step_index}"
                )
            total_power_uw = to_float(
                chiplet_samples[step_index]['total_power_uW'],
                "total_power_uW",
            )
            row.append(total_power_uw / 1e6)
        rows.append(row)

    return header, rows, step_size_us


def write_ptrace(path: Path, header: List[str], rows: List[List[float]]) -> None:
    if not rows:
        raise ValueError("Power trace must contain at least one row")
    lines = ["\t".join(header)]
    for row in rows:
        lines.append("\t".join(f"{value:.12g}" for value in row))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_hotspot(
    example_dir: Path,
    sampling_intvl_s: float,
    steady_only: bool,
    env: Dict[str, str],
) -> None:
    if sampling_intvl_s <= 0:
        raise ValueError(f"sampling_intvl_s must be > 0, got {sampling_intvl_s}")

    base_cmd = [
        str(HOTSPOT),
        "-c",
        DEFAULT_CONFIG_NAME,
        "-f",
        DEFAULT_FLP_NAME,
        "-p",
        DEFAULT_PTRACE_NAME,
        "-model_type",
        "block",
        "-sampling_intvl",
        f"{sampling_intvl_s:.12g}",
    ]

    first_cmd = base_cmd + [
        "-steady_file",
        str(Path(DEFAULT_OUTPUT_DIRNAME) / "example7.steady"),
        "-o",
        str(Path(DEFAULT_OUTPUT_DIRNAME) / "example7.ttrace"),
    ]
    run_checked(first_cmd, example_dir, env)

    if steady_only:
        return

    steady_path = example_dir / DEFAULT_OUTPUT_DIRNAME / "example7.steady"
    init_path = example_dir / DEFAULT_INIT_NAME
    shutil.copyfile(steady_path, init_path)

    second_cmd = base_cmd + [
        "-init_file",
        DEFAULT_INIT_NAME,
        "-o",
        str(Path(DEFAULT_OUTPUT_DIRNAME) / "example7.ttrace"),
    ]
    run_checked(second_cmd, example_dir, env)


def run_solvers(example_dir: Path, sampling_intvl_s: float, options: Dict[str, Any],
                env: Dict[str, str], extra_args: Optional[List[str]] = None) -> Dict[str, str]:
    """Independent steady/cold runs; periodic replay keeps all state in HotSpot."""
    choices = {'solver': {'steady','transient','both'}, 'workload': {'runtime','periodic','all_tiles'},
               'model_type': {'block','grid'}, 'init': {'ambient','mean_steady'}}
    for field, allowed in choices.items():
        if options[field] not in allowed:
            raise ValueError(f'Invalid thermal {field}: {options[field]!r}')
    if not math.isfinite(sampling_intvl_s) or sampling_intvl_s <= 0:
        raise ValueError('sampling_intvl_s must be positive and finite')
    if options['workload'] == 'periodic' and options['init'] != 'mean_steady':
        raise ValueError('periodic requires mean_steady initialization; ambient requires finite runtime workload')
    requested_record_us = options['record_step_us'] if 'record_step_us' in options else 1.0
    if not math.isfinite(requested_record_us) or requested_record_us <= 0:
        raise ValueError('record_step_us must be positive and finite')
    output = example_dir / DEFAULT_OUTPUT_DIRNAME
    output.mkdir(parents=True, exist_ok=True)
    rows, cols = options['grid'].split('x')
    base = [str(HOTSPOT), '-c', DEFAULT_CONFIG_NAME, '-f', DEFAULT_FLP_NAME,
            '-model_type', options['model_type'], '-grid_rows', rows, '-grid_cols', cols,
            '-sampling_intvl', f'{sampling_intvl_s:.12g}'] + (extra_args if extra_args is not None else [])
    result = {}
    (output / 'hotspot.log').write_text('', encoding='utf-8')
    if options['solver'] in {'steady', 'both'}:
        steady = output / 'mean.steady'
        command = base + ['-p', 'mean.ptrace', '-precise_steady_file', str(steady)]
        if options['model_type'] == 'grid':
            command += ['-grid_steady_file', str(output / 'mean.grid.steady')]
        run_checked(command, example_dir, env)
        result['steady_file'] = str(steady)
    if options['solver'] in {'transient', 'both'}:
        label = 'periodic' if options['workload'] == 'periodic' else 'cold'
        transient = output / (label + '.ttrace')
        statistics = output / (label + '.statistics.json')
        record_times = output / (label + '.record_times.csv')
        curve = output / (label + '.curve.csv')
        command = base + ['-p', DEFAULT_PTRACE_NAME, '-o', str(transient),
                         '-mean_steady_init', '1' if options['init'] == 'mean_steady' else '0',
                         '-record_intvl', str(max(requested_record_us*1e-6, sampling_intvl_s)),
                         '-transient_statistics', str(statistics), '-record_times', str(record_times),
                         '-temperature_curve', str(curve)]
        if options['workload'] == 'periodic':
            command += ['-periodic', '1', '-periodic_metadata', str(output / 'periodic.json')]
        if options['model_type'] == 'grid':
            peak_snapshot = output / (label + '.grid.peak_instant')
            command += ['-grid_peak_file', str(output / (label + '.grid.peak')),
                        '-grid_peak_snapshot', str(peak_snapshot)]
            result['peak_snapshot_file'] = str(peak_snapshot)
        run_checked(command, example_dir, env)
        result['transient_file'] = str(transient)
        result['transient_statistics_file'] = str(statistics)
        result['record_times_file'] = str(record_times)
        result['temperature_curve_file'] = str(curve)
    return result


def validate_prepared_options(data: Dict[str, Any], options: Dict[str, Any]) -> None:
    if options['structure'] != '2d' or options['leakage_json'] is not None or options['package_json'] is not None:
        raise ValueError('Prepared trace CLI cannot change physical package/leakage; use ThermalManager CLI')
    if data['workload'] != options['workload']:
        raise ValueError(f'Prepared trace workload {data["workload"]!r} differs from requested {options["workload"]!r}; use ThermalManager to regenerate')
    if options['duration_us'] is not None and not math.isclose(options['duration_us'], data['global_end_us']-data['global_start_us'], rel_tol=1e-9):
        raise ValueError('Prepared trace duration differs from requested duration; use ThermalManager to regenerate')


def main() -> int:
    sys.path.insert(0, str(REPO_ROOT.parents[1]))
    from chip.thermal.options import add_thermal_arguments, thermal_options
    parser = argparse.ArgumentParser(description="Generate and run HotSpot example7")
    parser.add_argument(
        "--power-timeseries-json",
        required=True,
        help="Path to chiplet_power_timeseries.json",
    )
    parser.add_argument(
        "--geometry-json",
        help=(
            "Path to geometry JSON with blocks[]. Required when example7.flp "
            "does not already exist or when --rewrite-floorplan is used."
        ),
    )
    parser.add_argument(
        "--example-dir",
        default=str(DEFAULT_EXAMPLE_DIR),
        help="HotSpot example7 directory",
    )
    parser.add_argument(
        "--rewrite-floorplan",
        action="store_true",
        help="Rewrite example7.flp from --geometry-json instead of reusing it",
    )
    parser.add_argument(
        "--sampling-interval-s",
        type=float,
        default=None,
        help="Override HotSpot sampling interval in seconds; default derives from step_size_us",
    )
    parser.add_argument(
        "--steady-only",
        action="store_true",
        help="Only run the first pass that writes steady output",
    )
    parser.add_argument('--legacy-preheated', action='store_true', help='Deprecated v1 two-pass replay for existing mode1 API')
    add_thermal_arguments(parser)
    args = parser.parse_args()

    env = ensure_runtime_path()
    example_dir = Path(args.example_dir)
    config_path = example_dir / DEFAULT_CONFIG_NAME
    flp_path = example_dir / DEFAULT_FLP_NAME
    ptrace_path = example_dir / DEFAULT_PTRACE_NAME

    assert_file(HOTSPOT)
    assert_file(config_path)

    if flp_path.exists() and not args.rewrite_floorplan:
        print(f"Reusing floorplan: {flp_path}")
        blocks = read_floorplan(flp_path)
    else:
        if not args.geometry_json:
            raise FileNotFoundError(
                "example7.flp is missing or --rewrite-floorplan was requested, "
                "but --geometry-json was not provided"
            )
        geometry_path = Path(args.geometry_json)
        print(f"Writing floorplan from geometry: {geometry_path}")
        blocks = load_geometry_blocks(geometry_path)
        write_floorplan(flp_path, blocks)

    power_timeseries_path = Path(args.power_timeseries_json)
    print(f"Loading power timeseries: {power_timeseries_path}")
    power_timeseries = load_json(power_timeseries_path)
    header, rows, step_size_us = build_ptrace_rows(blocks, power_timeseries, legacy_time_axis=args.legacy_preheated)
    options = None
    if not args.legacy_preheated:
        options = thermal_options(vars(args))
        if args.steady_only:
            options['solver'] = 'steady'
        validate_prepared_options(power_timeseries, options)
    reset_outputs(example_dir)

    print(f"Writing power trace: {ptrace_path}")
    write_ptrace(ptrace_path, header, rows)

    sampling_intvl_s = (
        args.sampling_interval_s
        if args.sampling_interval_s is not None
        else step_size_us * 1e-6
    )
    print(
        "Running HotSpot example7 "
        f"(samples={len(rows)}, step_size_us={step_size_us}, sampling_intvl_s={sampling_intvl_s})"
    )
    if args.legacy_preheated:
        print('WARNING: deprecated legacy preheated one-pass replay; use explicit thermal solvers. Removal follows mode1 caller migration.')
        run_hotspot(example_dir, sampling_intvl_s, args.steady_only, env)
    else:
        means = [math.fsum(row[i] for row in rows)/len(rows) for i in range(len(header))]
        write_ptrace(example_dir / 'mean.ptrace', header, [means])
        run_solvers(example_dir, sampling_intvl_s, options, env)
    print(f"Done. Outputs are under: {example_dir / DEFAULT_OUTPUT_DIRNAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
