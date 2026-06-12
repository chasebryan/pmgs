from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ToolCheck:
    name: str
    purpose: str
    path: str | None
    probe_status: str | None = None
    probe_output: str | None = None

    @property
    def available(self) -> bool:
        return self.path is not None


KNOWN_TOOLS: tuple[tuple[str, str], ...] = (
    ("rtl_test", "RTL-SDR hardware probe"),
    ("rtl_sdr", "raw IQ capture"),
    ("rtl_tcp", "networked RTL-SDR source"),
    ("SoapySDRUtil", "SoapySDR device probe"),
    ("satdump", "satellite decoder suite"),
    ("gr_satellites", "amateur satellite telemetry decoder"),
)


def scan_tools(*, probe: bool = False, timeout_seconds: float = 5.0) -> list[ToolCheck]:
    checks: list[ToolCheck] = []
    for name, purpose in KNOWN_TOOLS:
        path = shutil.which(name)
        probe_status = None
        probe_output = None
        if probe and name == "rtl_test" and path:
            probe_status, probe_output = _probe_rtl_test(path, timeout_seconds)
        checks.append(
            ToolCheck(
                name=name,
                purpose=purpose,
                path=path,
                probe_status=probe_status,
                probe_output=probe_output,
            )
        )
    return checks


def _probe_rtl_test(path: str, timeout_seconds: float) -> tuple[str, str]:
    try:
        completed = subprocess.run(
            [path, "-t"],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") + (exc.stderr or "")
        return "timeout", output.strip()
    except OSError as exc:
        return "error", str(exc)

    output = (completed.stdout or "") + (completed.stderr or "")
    status = "ok" if completed.returncode == 0 else f"exit {completed.returncode}"
    return status, output.strip()


def format_scan(checks: list[ToolCheck], *, as_json: bool = False) -> str:
    if as_json:
        return json.dumps(
            [asdict(check) | {"available": check.available} for check in checks],
            indent=2,
        )

    name_width = max(len("tool"), *(len(check.name) for check in checks))
    status_width = len("available")
    lines = [f"{'tool':<{name_width}}  {'available':<{status_width}}  purpose"]
    lines.append(f"{'-' * name_width}  {'-' * status_width}  -------")
    for check in checks:
        available = "yes" if check.available else "no"
        suffix = f" ({check.probe_status})" if check.probe_status else ""
        lines.append(
            f"{check.name:<{name_width}}  "
            f"{available:<{status_width}}  "
            f"{check.purpose}{suffix}"
        )
    return "\n".join(lines)
