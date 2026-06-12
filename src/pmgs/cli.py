from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Sequence

from . import __version__
from .antenna import ANTENNAS, render_guide
from .capture import CapturePlan, decoder_command, rtl_sdr_command, run_command, shell_join
from .catalog import format_targets
from .devices import format_scan, scan_tools
from .orbits import OrbitDependencyError, format_passes, predict_passes
from .reports import load_observation, write_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pmgs",
        description="Poor Man's Ground Station: RTL-SDR stock antenna satellite helper.",
    )
    parser.add_argument("--version", action="version", version=f"pmgs {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="detect local SDR and decoder tools")
    scan.add_argument("--probe", action="store_true", help="run rtl_test -t when available")
    scan.add_argument("--json", action="store_true", help="print machine-readable output")
    scan.set_defaults(func=_cmd_scan)

    antenna = subparsers.add_parser("antenna", help="show stock antenna setup guidance")
    antenna.add_argument("profile", choices=sorted(ANTENNAS), nargs="?", default="stock-dipole")
    antenna.add_argument("--band", choices=["vhf", "uhf"], default="vhf")
    antenna.set_defaults(func=_cmd_antenna)

    targets = subparsers.add_parser("targets", help="list beginner receive target profiles")
    targets.set_defaults(func=_cmd_targets)

    passes = subparsers.add_parser("passes", help="show realistic satellite pass candidates")
    passes.add_argument("--lat", type=float, required=True, help="observer latitude in decimal degrees")
    passes.add_argument("--lon", type=float, required=True, help="observer longitude in decimal degrees")
    passes.add_argument("--hours", type=float, default=12.0, help="planning window length")
    passes.add_argument("--min-elevation", type=float, default=25.0, help="minimum max elevation")
    passes.add_argument("--group", default="weather", choices=["weather", "amateur", "active"])
    passes.add_argument("--tle-file", type=Path, help="local TLE file instead of downloading CelesTrak data")
    passes.add_argument("--start", help="UTC ISO timestamp for deterministic planning")
    passes.add_argument("--limit", type=int, default=10)
    passes.add_argument("--antenna", choices=sorted(ANTENNAS), default="stock-dipole")
    passes.add_argument("--json", action="store_true")
    passes.set_defaults(func=_cmd_passes)

    capture = subparsers.add_parser("capture", help="prepare or run an rtl_sdr capture")
    capture.add_argument("--satellite", required=True)
    capture.add_argument("--frequency-mhz", type=float, required=True)
    capture.add_argument("--duration", type=int, required=True, help="duration in seconds")
    capture.add_argument("--output", type=Path, required=True)
    capture.add_argument("--sample-rate", type=int, default=1_024_000)
    capture.add_argument("--gain-db", type=float, default=36.4)
    capture.add_argument("--ppm", type=int)
    capture.add_argument("--device-index", type=int, default=0)
    capture.add_argument("--execute", action="store_true", help="run rtl_sdr instead of printing a dry run")
    capture.set_defaults(func=_cmd_capture)

    decode = subparsers.add_parser("decode", help="prepare or run a decoder handoff")
    decode.add_argument("--decoder", choices=["satdump", "gr-satellites"], required=True)
    decode.add_argument("--pipeline", required=True, help="decoder-specific pipeline/profile name")
    decode.add_argument("--input", type=Path, required=True)
    decode.add_argument("--output", type=Path, required=True)
    decode.add_argument("--extra-arg", action="append", default=[])
    decode.add_argument("--execute", action="store_true", help="run the decoder instead of printing a dry run")
    decode.set_defaults(func=_cmd_decode)

    report = subparsers.add_parser("report", help="generate a local HTML observation report")
    report.add_argument("--input", type=Path, required=True, help="observation JSON file")
    report.add_argument("--output", type=Path, required=True, help="HTML report path")
    report.set_defaults(func=_cmd_report)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except (KeyError, ValueError, OrbitDependencyError, OSError, json.JSONDecodeError) as exc:
        parser.exit(2, f"pmgs: error: {exc}\n")


def _cmd_scan(args: argparse.Namespace) -> int:
    print(format_scan(scan_tools(probe=args.probe), as_json=args.json))
    return 0


def _cmd_antenna(args: argparse.Namespace) -> int:
    print(render_guide(args.profile, band=args.band))
    return 0


def _cmd_targets(_args: argparse.Namespace) -> int:
    print(format_targets())
    return 0


def _cmd_passes(args: argparse.Namespace) -> int:
    start = _parse_datetime(args.start) if args.start else None
    candidates = predict_passes(
        latitude=args.lat,
        longitude=args.lon,
        hours=args.hours,
        min_elevation=args.min_elevation,
        group=args.group,
        tle_file=args.tle_file,
        start=start,
        limit=args.limit,
        antenna=args.antenna,
    )
    print(format_passes(candidates, as_json=args.json))
    return 0


def _cmd_capture(args: argparse.Namespace) -> int:
    plan = CapturePlan(
        satellite=args.satellite,
        frequency_mhz=args.frequency_mhz,
        duration_seconds=args.duration,
        output_path=args.output,
        sample_rate=args.sample_rate,
        gain_db=args.gain_db,
        ppm=args.ppm,
        device_index=args.device_index,
    )
    command = rtl_sdr_command(plan)
    print(f"Satellite: {plan.satellite}")
    print(shell_join(command))
    if not args.execute:
        print("Dry run only. Add --execute to record.")
        return 0
    return run_command(command)


def _cmd_decode(args: argparse.Namespace) -> int:
    command = decoder_command(
        decoder=args.decoder,
        pipeline=args.pipeline,
        input_path=args.input,
        output_path=args.output,
        extra_args=tuple(args.extra_arg),
    )
    print(shell_join(command))
    if not args.execute:
        print("Dry run only. Verify this template against your decoder version before using --execute.")
        return 0
    return run_command(command)


def _cmd_report(args: argparse.Namespace) -> int:
    observation = load_observation(args.input)
    output = write_report(observation, args.output)
    print(output)
    return 0


def _parse_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)
