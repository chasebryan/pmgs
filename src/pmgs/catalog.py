from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TargetProfile:
    """A beginner-facing receive target profile."""

    key: str
    label: str
    band: str
    decoder: str
    typical_frequency_mhz: str
    min_good_elevation: float
    antenna_hint: str
    notes: str


@dataclass(frozen=True)
class Recommendation:
    verdict: str
    difficulty: str
    score: int
    reason: str


STARTER_TARGETS: tuple[TargetProfile, ...] = (
    TargetProfile(
        key="meteor-lrpt",
        label="Meteor-M LRPT weather image",
        band="vhf",
        decoder="SatDump",
        typical_frequency_mhz="around 137 MHz; verify the current satellite list",
        min_good_elevation=30.0,
        antenna_hint="stock dipole in a shallow V, outside or at a clear window",
        notes="Good first weather-imagery target when an active LRPT satellite is supported.",
    ),
    TargetProfile(
        key="iss-aprs",
        label="ISS APRS / amateur packet activity",
        band="vhf",
        decoder="Dire Wolf or gr-satellites when applicable",
        typical_frequency_mhz="145.825 MHz when the service is active",
        min_good_elevation=25.0,
        antenna_hint="stock dipole vertical or shallow V, clear view of sky",
        notes="Schedules and modes vary; confirm current operations before a pass.",
    ),
    TargetProfile(
        key="amateur-telemetry",
        label="Amateur satellite telemetry",
        band="uhf",
        decoder="gr-satellites",
        typical_frequency_mhz="varies by satellite",
        min_good_elevation=45.0,
        antenna_hint="stock whip/dipole may hear strong passes, but UHF is less forgiving",
        notes="Good for experimentation; decoding success depends heavily on satellite and antenna placement.",
    ),
    TargetProfile(
        key="signal-only",
        label="Signal-only capture",
        band="mixed",
        decoder="none",
        typical_frequency_mhz="use target documentation",
        min_good_elevation=20.0,
        antenna_hint="best available stock antenna orientation for the target band",
        notes="Useful when PMGS can confirm a signal even if no decoder succeeds.",
    ),
)


def target_for_satellite(name: str) -> TargetProfile:
    lowered = name.lower()
    if "meteor" in lowered:
        return get_target("meteor-lrpt")
    if "iss" in lowered or "zarya" in lowered:
        return get_target("iss-aprs")
    if any(token in lowered for token in ("cubesat", "fox", "ao-", "so-", "rs-", "telemetry")):
        return get_target("amateur-telemetry")
    return get_target("signal-only")


def get_target(key: str) -> TargetProfile:
    for profile in STARTER_TARGETS:
        if profile.key == key:
            return profile
    known = ", ".join(profile.key for profile in STARTER_TARGETS)
    raise KeyError(f"unknown target profile {key!r}; known profiles: {known}")


def recommend_pass(
    *,
    max_elevation: float,
    profile: TargetProfile,
    antenna: str = "stock-dipole",
) -> Recommendation:
    score = 0
    reasons: list[str] = []

    if max_elevation >= profile.min_good_elevation + 20:
        score += 3
        reasons.append("high elevation gives the stock antenna more margin")
    elif max_elevation >= profile.min_good_elevation:
        score += 2
        reasons.append("elevation is good enough for a beginner attempt")
    elif max_elevation >= max(10.0, profile.min_good_elevation - 15):
        score += 1
        reasons.append("low elevation makes this a marginal stock-antenna attempt")
    else:
        reasons.append("elevation is too low for a realistic first attempt")

    antenna_key = antenna.lower().replace("_", "-")
    if profile.band == "vhf" and antenna_key in {"stock-dipole", "dipole"}:
        score += 1
        reasons.append("the stock dipole is the better kit antenna for this VHF target")
    elif profile.band == "uhf" and antenna_key in {"stock-whip", "whip"}:
        score += 1
        reasons.append("the stock whip can work for strong UHF passes")
    elif profile.band != "mixed":
        reasons.append("antenna choice is workable but not ideal")

    if score >= 4:
        return Recommendation("try this pass", "good", score, "; ".join(reasons))
    if score >= 2:
        return Recommendation("try only if convenient", "marginal", score, "; ".join(reasons))
    return Recommendation("skip for now", "poor", score, "; ".join(reasons))


def format_targets() -> str:
    lines = ["Beginner target profiles:"]
    for profile in STARTER_TARGETS:
        lines.extend(
            [
                f"",
                f"{profile.key}: {profile.label}",
                f"  Band: {profile.band}",
                f"  Typical frequency: {profile.typical_frequency_mhz}",
                f"  Decoder: {profile.decoder}",
                f"  Antenna: {profile.antenna_hint}",
                f"  Notes: {profile.notes}",
            ]
        )
    return "\n".join(lines)
