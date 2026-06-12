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
pmgs verify --input meteor.iq
pmgs decode --decoder satdump --pipeline meteor-lrpt --input meteor.iq --output decoded/
pmgs report --input observation.json --output report.html
```

Capture and decoder commands default to dry-run output. Add `--execute` only
after inspecting the command PMGS prints. Capture dry runs show the planned
duration, estimated IQ output size, and metadata sidecar path. Executed captures
write a `*.pmgs.json` sidecar by default and refuse to overwrite existing IQ
files unless `--overwrite` is passed.

## Basic Field Workflow

1. Confirm your tools and hardware are visible:

```bash
pmgs scan --probe
```

2. Set up the stock antenna for the band:

```bash
pmgs antenna stock-dipole --band vhf
```

3. Scan for realistic satellite passes:

```bash
pmgs passes --lat 41.8781 --lon -87.6298 --hours 12 --min-elevation 25
```

4. Dry-run the capture first. PMGS will show the exact `rtl_sdr` command,
   duration, expected IQ size, and metadata sidecar path:

```bash
pmgs capture \
  --satellite METEOR-M2-4 \
  --frequency-mhz 137.9 \
  --duration 600 \
  --output captures/meteor-m2-4.iq
```

5. If the dry run looks right, execute the capture:

```bash
pmgs capture \
  --satellite METEOR-M2-4 \
  --frequency-mhz 137.9 \
  --duration 600 \
  --output captures/meteor-m2-4.iq \
  --execute
```

6. Verify the capture before decoding:

```bash
pmgs verify --input captures/meteor-m2-4.iq
```

Verification checks the file size, sample count, PMGS metadata sidecar, estimated
duration, and a sampled slice of the unsigned 8-bit I/Q byte stream. A missing
metadata sidecar can still be inspected with an explicit sample rate:

```bash
pmgs verify --input meteor.iq --sample-rate 1024000
```

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
