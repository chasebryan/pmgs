from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CapturePlan:
    satellite: str
    frequency_mhz: float
    duration_seconds: int
    output_path: Path
    sample_rate: int = 1_024_000
    gain_db: float | None = 36.4
    ppm: int | None = None
    device_index: int = 0


def rtl_sdr_command(plan: CapturePlan) -> list[str]:
    frequency_hz = int(plan.frequency_mhz * 1_000_000)
    sample_count = max(1, int(plan.sample_rate * plan.duration_seconds))
    command = [
        "rtl_sdr",
        "-d",
        str(plan.device_index),
        "-f",
        str(frequency_hz),
        "-s",
        str(plan.sample_rate),
        "-n",
        str(sample_count),
    ]
    if plan.gain_db is not None:
        command.extend(["-g", f"{plan.gain_db:g}"])
    if plan.ppm is not None:
        command.extend(["-p", str(plan.ppm)])
    command.append(str(plan.output_path))
    return command


def shell_join(command: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in command)


def run_command(command: list[str]) -> int:
    completed = subprocess.run(command, check=False)
    return completed.returncode


def decoder_command(
    *,
    decoder: str,
    pipeline: str,
    input_path: Path,
    output_path: Path,
    extra_args: tuple[str, ...] = (),
) -> list[str]:
    decoder_key = decoder.lower()
    if decoder_key == "satdump":
        return ["satdump", pipeline, str(input_path), str(output_path), *extra_args]
    if decoder_key in {"gr-satellites", "gr_satellites"}:
        return ["gr_satellites", pipeline, "--iq-file", str(input_path), "--outdir", str(output_path), *extra_args]
    raise ValueError("decoder must be 'satdump' or 'gr-satellites'")
