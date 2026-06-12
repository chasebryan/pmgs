from __future__ import annotations

import json
import shlex
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RTL_SDR_BYTES_PER_COMPLEX_SAMPLE = 2


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


def sample_count(plan: CapturePlan) -> int:
    return max(1, int(plan.sample_rate * plan.duration_seconds))


def estimated_output_bytes(plan: CapturePlan) -> int:
    return sample_count(plan) * RTL_SDR_BYTES_PER_COMPLEX_SAMPLE


def format_duration(seconds: int) -> str:
    minutes, remaining_seconds = divmod(max(0, seconds), 60)
    hours, remaining_minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {remaining_minutes}m {remaining_seconds}s"
    if minutes:
        return f"{minutes}m {remaining_seconds}s"
    return f"{remaining_seconds}s"


def format_bytes(byte_count: int) -> str:
    value = float(byte_count)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024.0 or unit == "TiB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024.0
    raise AssertionError("unreachable")


def rtl_sdr_command(plan: CapturePlan) -> list[str]:
    frequency_hz = int(plan.frequency_mhz * 1_000_000)
    command = [
        "rtl_sdr",
        "-d",
        str(plan.device_index),
        "-f",
        str(frequency_hz),
        "-s",
        str(plan.sample_rate),
        "-n",
        str(sample_count(plan)),
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


def default_metadata_path(output_path: Path) -> Path:
    return output_path.with_suffix(output_path.suffix + ".pmgs.json")


def run_capture(
    *,
    plan: CapturePlan,
    command: list[str],
    metadata_path: Path | None,
    overwrite: bool = False,
    progress_interval: int = 30,
) -> int:
    output_path = Path(plan.output_path)
    if output_path.exists() and not overwrite:
        raise ValueError(
            f"output file already exists: {output_path}; choose a new path or pass --overwrite"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if metadata_path is not None:
        metadata_path.parent.mkdir(parents=True, exist_ok=True)

    started_at = datetime.now(timezone.utc)
    process = subprocess.Popen(command)
    exit_code = _wait_with_progress(
        process=process,
        duration_seconds=plan.duration_seconds,
        progress_interval=progress_interval,
    )
    ended_at = datetime.now(timezone.utc)

    if metadata_path is not None:
        metadata = capture_metadata(
            plan=plan,
            command=command,
            started_at=started_at,
            ended_at=ended_at,
            exit_code=exit_code,
            actual_output_bytes=output_path.stat().st_size if output_path.exists() else None,
        )
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return exit_code


def _wait_with_progress(
    *,
    process: subprocess.Popen[Any],
    duration_seconds: int,
    progress_interval: int,
) -> int:
    start_monotonic = time.monotonic()
    next_progress = float(max(1, progress_interval))
    try:
        while True:
            exit_code = process.poll()
            elapsed = time.monotonic() - start_monotonic
            if exit_code is not None:
                return int(exit_code)
            if elapsed >= next_progress:
                print(
                    "PMGS capture progress: "
                    f"{format_duration(int(elapsed))} / {format_duration(duration_seconds)}"
                )
                next_progress += max(1, progress_interval)
            time.sleep(1)
    except KeyboardInterrupt:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        print("PMGS capture interrupted; partial output may still be useful.")
        return 130


def capture_metadata(
    *,
    plan: CapturePlan,
    command: list[str],
    started_at: datetime,
    ended_at: datetime,
    exit_code: int,
    actual_output_bytes: int | None,
) -> dict[str, object]:
    return {
        "schema": "pmgs.capture.v1",
        "satellite": plan.satellite,
        "frequency_mhz": plan.frequency_mhz,
        "duration_seconds": plan.duration_seconds,
        "sample_rate": plan.sample_rate,
        "gain_db": plan.gain_db,
        "ppm": plan.ppm,
        "device_index": plan.device_index,
        "output_path": str(plan.output_path),
        "estimated_output_bytes": estimated_output_bytes(plan),
        "actual_output_bytes": actual_output_bytes,
        "command": command,
        "started_at": started_at.isoformat(),
        "ended_at": ended_at.isoformat(),
        "exit_code": exit_code,
    }


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
        return [
            "gr_satellites",
            pipeline,
            "--iq-file",
            str(input_path),
            "--outdir",
            str(output_path),
            *extra_args,
        ]
    raise ValueError("decoder must be 'satdump' or 'gr-satellites'")
