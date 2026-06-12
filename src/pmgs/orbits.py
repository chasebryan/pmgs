from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .catalog import Recommendation, recommend_pass, target_for_satellite


CELESTRAK_GROUPS: dict[str, str] = {
    "weather": "https://celestrak.org/NORAD/elements/gp.php?GROUP=weather&FORMAT=tle",
    "amateur": "https://celestrak.org/NORAD/elements/gp.php?GROUP=amateur&FORMAT=tle",
    "active": "https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle",
}


class OrbitDependencyError(RuntimeError):
    pass


@dataclass(frozen=True)
class PassCandidate:
    satellite: str
    aos: str
    tca: str
    los: str
    max_elevation: float
    azimuth_at_tca: float
    target_key: str
    target_label: str
    frequency_hint: str
    decoder: str
    verdict: str
    difficulty: str
    score: int
    reason: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def read_tle_text(
    *,
    group: str = "weather",
    tle_file: Path | None = None,
    timeout_seconds: int = 15,
) -> str:
    if tle_file is not None:
        return tle_file.read_text(encoding="utf-8")
    if group not in CELESTRAK_GROUPS:
        known = ", ".join(sorted(CELESTRAK_GROUPS))
        raise ValueError(f"unknown CelesTrak group {group!r}; known groups: {known}")
    try:
        with urllib.request.urlopen(CELESTRAK_GROUPS[group], timeout=timeout_seconds) as response:
            return response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise ValueError(f"could not fetch CelesTrak TLE data for group {group!r}: {exc}") from exc


def parse_tles(tle_text: str) -> list[tuple[str, str, str]]:
    lines = [line.strip() for line in tle_text.splitlines() if line.strip()]
    triples: list[tuple[str, str, str]] = []
    index = 0
    while index + 2 < len(lines):
        name, line1, line2 = lines[index], lines[index + 1], lines[index + 2]
        if line1.startswith("1 ") and line2.startswith("2 "):
            triples.append((name, line1, line2))
            index += 3
        else:
            index += 1
    return triples


def predict_passes(
    *,
    latitude: float,
    longitude: float,
    hours: float,
    min_elevation: float,
    group: str = "weather",
    tle_file: Path | None = None,
    start: datetime | None = None,
    limit: int = 10,
    antenna: str = "stock-dipole",
) -> list[PassCandidate]:
    try:
        from skyfield.api import EarthSatellite, load, wgs84
    except ModuleNotFoundError as exc:
        raise OrbitDependencyError(
            "real pass prediction requires the optional Skyfield dependency; "
            "install with: python -m pip install -e '.[orbit]'"
        ) from exc

    start_dt = _ensure_utc(start or datetime.now(timezone.utc))
    end_dt = start_dt + timedelta(hours=hours)
    tle_text = read_tle_text(group=group, tle_file=tle_file)
    tle_triples = parse_tles(tle_text)
    if not tle_triples:
        raise ValueError("no valid TLE triples found")

    ts = load.timescale()
    observer = wgs84.latlon(latitude, longitude)
    start_time = ts.from_datetime(start_dt)
    end_time = ts.from_datetime(end_dt)
    candidates: list[PassCandidate] = []

    for name, line1, line2 in tle_triples:
        satellite = EarthSatellite(line1, line2, name, ts)
        times, events = satellite.find_events(observer, start_time, end_time, altitude_degrees=0.0)
        active: dict[str, object] = {}
        for event_time, event in zip(times, events, strict=False):
            if event == 0:
                active = {"aos": event_time}
            elif event == 1 and active:
                alt, az, _distance = (satellite - observer).at(event_time).altaz()
                active["tca"] = event_time
                active["max_elevation"] = float(alt.degrees)
                active["azimuth_at_tca"] = float(az.degrees)
            elif event == 2 and active:
                active["los"] = event_time
                candidate = _candidate_from_events(
                    name=name,
                    active=active,
                    min_elevation=min_elevation,
                    antenna=antenna,
                )
                if candidate is not None:
                    candidates.append(candidate)
                active = {}

    candidates.sort(key=lambda item: (-item.score, item.tca, item.satellite))
    return candidates[:limit]


def _candidate_from_events(
    *,
    name: str,
    active: dict[str, object],
    min_elevation: float,
    antenna: str,
) -> PassCandidate | None:
    if not {"aos", "tca", "los", "max_elevation", "azimuth_at_tca"} <= set(active):
        return None
    max_elevation = float(active["max_elevation"])
    if max_elevation < min_elevation:
        return None
    profile = target_for_satellite(name)
    recommendation: Recommendation = recommend_pass(
        max_elevation=max_elevation,
        profile=profile,
        antenna=antenna,
    )
    return PassCandidate(
        satellite=name,
        aos=_skyfield_iso(active["aos"]),
        tca=_skyfield_iso(active["tca"]),
        los=_skyfield_iso(active["los"]),
        max_elevation=max_elevation,
        azimuth_at_tca=float(active["azimuth_at_tca"]),
        target_key=profile.key,
        target_label=profile.label,
        frequency_hint=profile.typical_frequency_mhz,
        decoder=profile.decoder,
        verdict=recommendation.verdict,
        difficulty=recommendation.difficulty,
        score=recommendation.score,
        reason=recommendation.reason,
    )


def _skyfield_iso(value: object) -> str:
    return value.utc_datetime().replace(tzinfo=timezone.utc).isoformat()


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def format_passes(candidates: list[PassCandidate], *, as_json: bool = False) -> str:
    if as_json:
        return json.dumps([candidate.to_dict() for candidate in candidates], indent=2)
    if not candidates:
        return "No realistic passes matched the current filters."

    lines = [
        "satellite                         "
        "tca UTC               "
        "elev  verdict                  freq"
    ]
    lines.append("-" * len(lines[0]))
    for candidate in candidates:
        satellite = candidate.satellite[:31]
        tca = candidate.tca.replace("+00:00", "Z")
        lines.append(
            f"{satellite:<31}  {tca:<20}  {candidate.max_elevation:>4.0f}  "
            f"{candidate.verdict:<23}  {candidate.frequency_hint}"
        )
    return "\n".join(lines)
