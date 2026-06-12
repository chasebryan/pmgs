from __future__ import annotations

import json
import shlex
import subprocess
import time
from dataclasses import dataclass, field
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


@dataclass(frozen=True)
class IQStats:
    sampled_complex_samples: int
    byte_min: int
    byte_max: int
    i_mean: float
    q_mean: float
    i_stddev: float
    q_stddev: float


@dataclass(frozen=True)
class CaptureVerification:
    input_path: Path
    file_bytes: int
    complex_samples: int
    metadata_path: Path | None = None
    metadata_found: bool = False
    sample_rate: int | None = None
    expected_bytes: int | None = None
    duration_seconds: float | None = None
    size_ratio: float | None = None
    iq_stats: IQStats | None = None
    verdict: str = "suspect"
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return self.verdict in {"complete", "partial"}


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


def load_capture_metadata(metadata_path: Path) -> dict[str, Any]:
    with metadata_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("capture metadata must be a JSON object")
    return data


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


def verify_capture(
    *,
    input_path: Path,
    metadata_path: Path | None = None,
    sample_rate: int | None = None,
    expected_bytes: int | None = None,
    max_sample_bytes: int = 1_048_576,
) -> CaptureVerification:
    if not input_path.exists():
        raise ValueError(f"capture file does not exist: {input_path}")

    metadata = None
    metadata_found = False
    resolved_metadata_path = metadata_path
    if resolved_metadata_path is None:
        candidate = default_metadata_path(input_path)
        resolved_metadata_path = candidate if candidate.exists() else None
    if resolved_metadata_path is not None and resolved_metadata_path.exists():
        metadata = load_capture_metadata(resolved_metadata_path)
        metadata_found = True

    metadata_sample_rate = _metadata_int(metadata, "sample_rate")
    metadata_expected_bytes = _metadata_int(metadata, "estimated_output_bytes")
    chosen_sample_rate = sample_rate or metadata_sample_rate
    chosen_expected_bytes = expected_bytes or metadata_expected_bytes

    file_bytes = input_path.stat().st_size
    complex_samples = file_bytes // RTL_SDR_BYTES_PER_COMPLEX_SAMPLE
    duration_seconds = None
    if chosen_sample_rate:
        duration_seconds = complex_samples / chosen_sample_rate

    size_ratio = None
    if chosen_expected_bytes:
        size_ratio = file_bytes / chosen_expected_bytes

    notes: list[str] = []
    if file_bytes == 0:
        notes.append("capture file is empty")
    if file_bytes % RTL_SDR_BYTES_PER_COMPLEX_SAMPLE:
        notes.append("capture byte count is odd; RTL-SDR IQ data should be I/Q byte pairs")
    if not metadata_found:
        notes.append("no PMGS metadata sidecar found; pass --metadata if this capture has one")
    if chosen_sample_rate is None:
        notes.append("sample rate is unknown; pass --sample-rate for a duration estimate")
    if chosen_expected_bytes is None:
        notes.append("expected size is unknown; pass --expected-bytes or use PMGS metadata")

    iq_stats = _sample_iq_stats(input_path, max_sample_bytes=max_sample_bytes)
    if iq_stats is None:
        notes.append("not enough IQ data to inspect")
    else:
        if iq_stats.byte_min == iq_stats.byte_max:
            notes.append("IQ bytes are flat; this does not look like a useful capture")
        if iq_stats.i_stddev < 1.0 and iq_stats.q_stddev < 1.0:
            notes.append("I/Q variation is extremely low; capture may be blank or stuck")

    verdict = _verification_verdict(
        file_bytes=file_bytes,
        expected_bytes=chosen_expected_bytes,
        iq_stats=iq_stats,
        notes=notes,
    )
    return CaptureVerification(
        input_path=input_path,
        file_bytes=file_bytes,
        complex_samples=complex_samples,
        metadata_path=resolved_metadata_path,
        metadata_found=metadata_found,
        sample_rate=chosen_sample_rate,
        expected_bytes=chosen_expected_bytes,
        duration_seconds=duration_seconds,
        size_ratio=size_ratio,
        iq_stats=iq_stats,
        verdict=verdict,
        notes=tuple(notes),
    )


def format_verification(result: CaptureVerification, *, as_json: bool = False) -> str:
    if as_json:
        return json.dumps(_verification_to_dict(result), indent=2)

    lines = [
        "PMGS Capture Verification",
        "=========================",
        f"File: {result.input_path}",
        f"Size: {format_bytes(result.file_bytes)}",
        f"Complex samples: {result.complex_samples:,}",
        f"Metadata: {_metadata_label(result)}",
    ]
    if result.sample_rate:
        lines.append(f"Sample rate: {result.sample_rate:,} S/s")
    if result.duration_seconds is not None:
        lines.append(f"Estimated duration: {format_duration(round(result.duration_seconds))}")
    if result.expected_bytes is not None:
        lines.append(f"Expected size: {format_bytes(result.expected_bytes)}")
    if result.size_ratio is not None:
        lines.append(f"Size ratio: {result.size_ratio:.1%}")
    if result.iq_stats is not None:
        stats = result.iq_stats
        lines.extend(
            [
                "",
                "IQ byte health:",
                f"  Sampled pairs: {stats.sampled_complex_samples:,}",
                f"  Byte range: {stats.byte_min}..{stats.byte_max}",
                f"  I mean/stddev: {stats.i_mean:.2f} / {stats.i_stddev:.2f}",
                f"  Q mean/stddev: {stats.q_mean:.2f} / {stats.q_stddev:.2f}",
            ]
        )
    lines.extend(["", f"Verdict: {result.verdict}"])
    if result.notes:
        lines.append("Notes:")
        lines.extend(f"- {note}" for note in result.notes)
    return "\n".join(lines)


def _verification_to_dict(result: CaptureVerification) -> dict[str, object]:
    return {
        "input_path": str(result.input_path),
        "file_bytes": result.file_bytes,
        "complex_samples": result.complex_samples,
        "metadata_path": None if result.metadata_path is None else str(result.metadata_path),
        "metadata_found": result.metadata_found,
        "sample_rate": result.sample_rate,
        "expected_bytes": result.expected_bytes,
        "duration_seconds": result.duration_seconds,
        "size_ratio": result.size_ratio,
        "iq_stats": None if result.iq_stats is None else result.iq_stats.__dict__,
        "verdict": result.verdict,
        "notes": list(result.notes),
    }


def _metadata_label(result: CaptureVerification) -> str:
    if result.metadata_found and result.metadata_path is not None:
        return f"found at {result.metadata_path}"
    if result.metadata_path is not None:
        return f"missing at {result.metadata_path}"
    return "not found"


def _metadata_int(metadata: dict[str, Any] | None, key: str) -> int | None:
    if metadata is None or metadata.get(key) is None:
        return None
    try:
        return int(metadata[key])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"metadata field {key!r} must be an integer") from exc


def _sample_iq_stats(input_path: Path, *, max_sample_bytes: int) -> IQStats | None:
    file_bytes = input_path.stat().st_size
    if file_bytes < RTL_SDR_BYTES_PER_COMPLEX_SAMPLE:
        return None

    chunk_size = max(RTL_SDR_BYTES_PER_COMPLEX_SAMPLE, max_sample_bytes // 8)
    chunk_size -= chunk_size % RTL_SDR_BYTES_PER_COMPLEX_SAMPLE
    chunk_size = max(RTL_SDR_BYTES_PER_COMPLEX_SAMPLE, chunk_size)
    offsets = _sample_offsets(file_bytes=file_bytes, chunk_size=chunk_size)

    stats = _RunningIQStats()
    with input_path.open("rb") as handle:
        for offset in offsets:
            aligned_offset = offset - (offset % RTL_SDR_BYTES_PER_COMPLEX_SAMPLE)
            handle.seek(aligned_offset)
            chunk = handle.read(chunk_size)
            if len(chunk) % RTL_SDR_BYTES_PER_COMPLEX_SAMPLE:
                chunk = chunk[:-1]
            stats.update(chunk)
    return stats.finish()


def _sample_offsets(*, file_bytes: int, chunk_size: int) -> list[int]:
    if file_bytes <= chunk_size:
        return [0]
    max_offset = max(0, file_bytes - chunk_size)
    return sorted({round(max_offset * index / 7) for index in range(8)})


class _RunningIQStats:
    def __init__(self) -> None:
        self.count = 0
        self.byte_min = 255
        self.byte_max = 0
        self.i_mean = 0.0
        self.q_mean = 0.0
        self.i_m2 = 0.0
        self.q_m2 = 0.0

    def update(self, chunk: bytes) -> None:
        for index in range(0, len(chunk), RTL_SDR_BYTES_PER_COMPLEX_SAMPLE):
            i_value = chunk[index]
            q_value = chunk[index + 1]
            self.byte_min = min(self.byte_min, i_value, q_value)
            self.byte_max = max(self.byte_max, i_value, q_value)
            self.count += 1
            self.i_mean, self.i_m2 = _welford_step(
                value=i_value,
                count=self.count,
                mean=self.i_mean,
                m2=self.i_m2,
            )
            self.q_mean, self.q_m2 = _welford_step(
                value=q_value,
                count=self.count,
                mean=self.q_mean,
                m2=self.q_m2,
            )

    def finish(self) -> IQStats | None:
        if self.count == 0:
            return None
        i_variance = self.i_m2 / (self.count - 1) if self.count > 1 else 0.0
        q_variance = self.q_m2 / (self.count - 1) if self.count > 1 else 0.0
        return IQStats(
            sampled_complex_samples=self.count,
            byte_min=self.byte_min,
            byte_max=self.byte_max,
            i_mean=self.i_mean,
            q_mean=self.q_mean,
            i_stddev=i_variance**0.5,
            q_stddev=q_variance**0.5,
        )


def _welford_step(*, value: int, count: int, mean: float, m2: float) -> tuple[float, float]:
    delta = value - mean
    mean += delta / count
    delta_after = value - mean
    m2 += delta * delta_after
    return mean, m2


def _verification_verdict(
    *,
    file_bytes: int,
    expected_bytes: int | None,
    iq_stats: IQStats | None,
    notes: list[str],
) -> str:
    if file_bytes == 0 or iq_stats is None:
        return "suspect"
    if iq_stats.byte_min == iq_stats.byte_max:
        return "suspect"
    if iq_stats.i_stddev < 1.0 and iq_stats.q_stddev < 1.0:
        return "suspect"
    if expected_bytes is None:
        return "partial"
    tolerance = max(RTL_SDR_BYTES_PER_COMPLEX_SAMPLE, round(expected_bytes * 0.01))
    if file_bytes + tolerance < expected_bytes:
        return "partial"
    if file_bytes > expected_bytes + tolerance:
        notes.append("capture is larger than expected; check sample rate/duration assumptions")
    return "complete"


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
