from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AntennaProfile:
    key: str
    label: str
    summary: str
    vhf_steps: tuple[str, ...]
    uhf_steps: tuple[str, ...]
    warnings: tuple[str, ...]


ANTENNAS: dict[str, AntennaProfile] = {
    "stock-dipole": AntennaProfile(
        key="stock-dipole",
        label="RTL-SDR stock dipole",
        summary="Best stock-kit starting point for VHF weather and amateur satellite attempts.",
        vhf_steps=(
            "Use both telescoping elements.",
            "Set each side roughly 50-55 cm for the 137 MHz weather-satellite band.",
            "Open the elements into a shallow V shape.",
            "Place it outside or at the clearest window with the broad side facing sky.",
            "Keep the feedline and laptop away from the elements when possible.",
        ),
        uhf_steps=(
            "Shorten both elements for UHF experiments.",
            "Prefer high-elevation passes; UHF stock antenna attempts have little margin.",
            "Move away from USB noise sources and indoor metal screens.",
        ),
        warnings=(
            "Indoor reception can work, but glass coatings and window screens often hurt badly.",
            "Do not judge the whole setup from one low-elevation pass.",
        ),
    ),
    "stock-whip": AntennaProfile(
        key="stock-whip",
        label="RTL-SDR stock whip",
        summary="Simple and portable, but less forgiving than the stock dipole for VHF satellite work.",
        vhf_steps=(
            "Fully extend the whip for VHF.",
            "Use a magnetic base on a metal surface if your kit includes one.",
            "Favor passes above 45 degrees elevation.",
            "Expect signal-only captures more often than clean decodes.",
        ),
        uhf_steps=(
            "Shorten the whip for UHF targets.",
            "Keep the antenna vertical for many amateur beacon attempts.",
            "Use high passes and record IQ even when live decode fails.",
        ),
        warnings=(
            "The whip is convenient, not magic; low passes are usually not worth first attempts.",
            "Touching the antenna or cable during a pass can change reception.",
        ),
    ),
}


def get_antenna(key: str) -> AntennaProfile:
    normalized = key.lower().replace("_", "-")
    if normalized in ANTENNAS:
        return ANTENNAS[normalized]
    known = ", ".join(sorted(ANTENNAS))
    raise KeyError(f"unknown antenna {key!r}; known antennas: {known}")


def render_guide(key: str, band: str = "vhf") -> str:
    profile = get_antenna(key)
    band_key = band.lower()
    if band_key not in {"vhf", "uhf"}:
        raise ValueError("band must be 'vhf' or 'uhf'")

    steps = profile.vhf_steps if band_key == "vhf" else profile.uhf_steps
    lines = [
        f"{profile.label}",
        "=" * len(profile.label),
        profile.summary,
        "",
        f"{band_key.upper()} setup:",
    ]
    lines.extend(f"{index}. {step}" for index, step in enumerate(steps, start=1))
    lines.append("")
    lines.append("Reality checks:")
    lines.extend(f"- {warning}" for warning in profile.warnings)
    return "\n".join(lines)
