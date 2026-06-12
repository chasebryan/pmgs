# PMGS

Poor Man's Ground Station.

PMGS is an all-in-one receive-only satellite ground-station suite for people
using cheap RTL-SDR hardware and the antenna that came in the box. It predicts
realistic passes, guides stock antenna setup, prepares capture commands, hands
recordings to existing decoders, and generates honest success/failure reports.

The project is intentionally an orchestrator. It does not try to replace
SatDump, gr-satellites, Gpredict, SatNOGS, or other mature radio tools.

## Scope

- Receive-only public, amateur, weather, educational, and openly decodable
  satellite signals.
- RTL-SDR-first workflows.
- Stock antenna realism over professional ground-station assumptions.
- Local reports that explain whether a pass was a good beginner target and
  what likely failed.

PMGS does not support transmitting, private communications collection, or
publishing intercepted private content.

## Install for Development

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

Optional real pass prediction uses Skyfield:

```bash
python -m pip install -e '.[orbit]'
```

## CLI

```bash
pmgs scan
pmgs antenna stock-dipole --band vhf
pmgs passes --lat 41.8781 --lon -87.6298 --hours 12 --min-elevation 25
pmgs capture --satellite METEOR-M --frequency-mhz 137.9 --duration 600 --output meteor.iq
pmgs decode --decoder satdump --pipeline meteor-lrpt --input meteor.iq --output decoded/
pmgs report --input observation.json --output report.html
```

Capture and decoder commands default to dry-run output. Add `--execute` only
after inspecting the command PMGS prints.

## Example Observation JSON

```json
{
  "satellite": "METEOR-M N2-4",
  "pass_time": "2026-06-11T22:18:00-05:00",
  "max_elevation": 64.0,
  "frequency_mhz": 137.9,
  "device": "RTL-SDR Blog V4",
  "antenna": "stock dipole V configuration",
  "location_note": "indoor window",
  "gain_db": 36.4,
  "signal_detected": true,
  "decode_attempted": true,
  "decode_result": "partial image",
  "snr_estimate": "weak/moderate",
  "recommendation": "try outside next pass",
  "artifacts": ["meteor.iq", "waterfall.png"]
}
```

Generate a report:

```bash
pmgs report --input observation.json --output report.html
```

## Development Checks

```bash
python -m unittest discover
python -m pmgs --help
```

## License

PMGS is licensed under GPL-3.0. See [LICENSE](LICENSE).

## Project Status

This is the initial scaffold for PMGS v0.1. Before publishing releases, verify
decoder command templates against the exact SatDump and gr-satellites versions
you want to support.
