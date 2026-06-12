from __future__ import annotations

import html
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Observation:
    satellite: str
    pass_time: str
    max_elevation: float
    frequency_mhz: float
    device: str
    antenna: str
    location_note: str
    gain_db: float | None = None
    signal_detected: bool | None = None
    decode_attempted: bool | None = None
    decode_result: str = "not recorded"
    snr_estimate: str = "not recorded"
    recommendation: str = "not recorded"
    artifacts: list[str] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "Observation":
        required = [
            "satellite",
            "pass_time",
            "max_elevation",
            "frequency_mhz",
            "device",
            "antenna",
            "location_note",
        ]
        missing = [key for key in required if key not in data]
        if missing:
            raise ValueError(f"observation JSON is missing required fields: {', '.join(missing)}")
        return cls(
            satellite=str(data["satellite"]),
            pass_time=str(data["pass_time"]),
            max_elevation=float(data["max_elevation"]),
            frequency_mhz=float(data["frequency_mhz"]),
            device=str(data["device"]),
            antenna=str(data["antenna"]),
            location_note=str(data["location_note"]),
            gain_db=None if data.get("gain_db") is None else float(data["gain_db"]),
            signal_detected=_optional_bool(data.get("signal_detected")),
            decode_attempted=_optional_bool(data.get("decode_attempted")),
            decode_result=str(data.get("decode_result", "not recorded")),
            snr_estimate=str(data.get("snr_estimate", "not recorded")),
            recommendation=str(data.get("recommendation", "not recorded")),
            artifacts=[str(item) for item in data.get("artifacts", [])],
        )


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1"}:
            return True
        if lowered in {"false", "no", "0"}:
            return False
    raise ValueError(f"expected boolean-like value, got {value!r}")


def load_observation(path: Path) -> Observation:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("observation JSON must be an object")
    return Observation.from_mapping(data)


def render_html_report(observation: Observation) -> str:
    rows = [
        ("Satellite", observation.satellite),
        ("Pass time", observation.pass_time),
        ("Max elevation", f"{observation.max_elevation:g} deg"),
        ("Frequency", f"{observation.frequency_mhz:g} MHz"),
        ("Device", observation.device),
        ("Antenna", observation.antenna),
        ("Location", observation.location_note),
        ("Gain", "not recorded" if observation.gain_db is None else f"{observation.gain_db:g} dB"),
        ("Signal detected", _format_bool(observation.signal_detected)),
        ("Decode attempted", _format_bool(observation.decode_attempted)),
        ("Decode result", observation.decode_result),
        ("SNR estimate", observation.snr_estimate),
        ("Recommendation", observation.recommendation),
    ]
    artifact_items = "\n".join(f"<li>{html.escape(item)}</li>" for item in observation.artifacts)
    if not artifact_items:
        artifact_items = "<li>none recorded</li>"

    row_html = "\n".join(_table_row(label, value) for label, value in rows)
    title = f"PMGS Report - {observation.satellite}"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{ color-scheme: light dark; font-family: ui-sans-serif, system-ui, sans-serif; }}
    body {{ margin: 2rem; line-height: 1.45; }}
    main {{ max-width: 860px; }}
    table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
    th, td {{
      border-bottom: 1px solid #8884;
      padding: 0.65rem;
      text-align: left;
      vertical-align: top;
    }}
    th {{ width: 12rem; }}
    .badge {{ display: inline-block; padding: 0.25rem 0.5rem; border: 1px solid #8886; }}
  </style>
</head>
<body>
  <main>
    <p class="badge">PMGS receive-only observation</p>
    <h1>{html.escape(observation.satellite)}</h1>
    <table>
      <tbody>
{row_html}
      </tbody>
    </table>
    <h2>Artifacts</h2>
    <ul>
{artifact_items}
    </ul>
  </main>
</body>
</html>
"""


def _format_bool(value: bool | None) -> str:
    if value is None:
        return "not recorded"
    return "yes" if value else "no"


def _table_row(label: str, value: str) -> str:
    return f"<tr><th>{html.escape(label)}</th><td>{html.escape(value)}</td></tr>"


def write_report(observation: Observation, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_html_report(observation), encoding="utf-8")
    return output_path
