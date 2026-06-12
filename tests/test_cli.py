from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

from pmgs import cli
from pmgs.capture import (
    CapturePlan,
    capture_metadata,
    estimated_output_bytes,
    rtl_sdr_command,
    run_capture,
    verify_capture,
)
from pmgs.catalog import get_target, recommend_pass


class CliTests(unittest.TestCase):
    def test_antenna_command_prints_stock_dipole_guide(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            status = cli.main(["antenna", "stock-dipole", "--band", "vhf"])
        self.assertEqual(status, 0)
        output = buffer.getvalue()
        self.assertIn("RTL-SDR stock dipole", output)
        self.assertIn("137 MHz", output)

    def test_capture_command_uses_duration_to_limit_sample_count(self) -> None:
        command = rtl_sdr_command(
            CapturePlan(
                satellite="METEOR-M",
                frequency_mhz=137.9,
                duration_seconds=10,
                output_path="meteor.iq",  # type: ignore[arg-type]
                sample_rate=1_024_000,
            )
        )
        self.assertIn("-n", command)
        self.assertEqual(command[command.index("-n") + 1], "10240000")

    def test_capture_estimates_iq_output_size(self) -> None:
        plan = CapturePlan(
            satellite="METEOR-M",
            frequency_mhz=137.9,
            duration_seconds=10,
            output_path="meteor.iq",  # type: ignore[arg-type]
            sample_rate=1_024_000,
        )
        self.assertEqual(estimated_output_bytes(plan), 20_480_000)

    def test_run_capture_refuses_existing_output_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "capture.iq"
            output.write_bytes(b"existing")
            plan = CapturePlan(
                satellite="METEOR-M",
                frequency_mhz=137.9,
                duration_seconds=1,
                output_path=output,
            )
            with self.assertRaisesRegex(ValueError, "already exists"):
                run_capture(
                    plan=plan,
                    command=["echo", "should-not-run"],
                    metadata_path=None,
                    overwrite=False,
                )

    def test_verify_capture_accepts_plausible_iq_with_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "capture.iq"
            output.write_bytes(bytes([0, 255, 64, 192, 128, 127, 192, 64]) * 256)
            plan = CapturePlan(
                satellite="METEOR-M",
                frequency_mhz=137.9,
                duration_seconds=1,
                output_path=output,
                sample_rate=1024,
            )
            metadata = capture_metadata(
                plan=plan,
                command=rtl_sdr_command(plan),
                started_at=datetime(2026, 6, 12, tzinfo=timezone.utc),
                ended_at=datetime(2026, 6, 12, 0, 0, 1, tzinfo=timezone.utc),
                exit_code=0,
                actual_output_bytes=output.stat().st_size,
            )
            metadata_path = root / "capture.iq.pmgs.json"
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

            result = verify_capture(input_path=output, metadata_path=metadata_path)

            self.assertEqual(result.verdict, "complete")
            self.assertTrue(result.metadata_found)
            self.assertEqual(result.sample_rate, 1024)

    def test_verify_capture_flags_flat_iq_as_suspect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "flat.iq"
            output.write_bytes(b"\x80\x80" * 128)

            result = verify_capture(input_path=output, sample_rate=1024)

            self.assertEqual(result.verdict, "suspect")
            self.assertIn("flat", " ".join(result.notes))

    def test_recommendation_scores_high_elevation_meteor_pass(self) -> None:
        profile = get_target("meteor-lrpt")
        recommendation = recommend_pass(
            max_elevation=65.0,
            profile=profile,
            antenna="stock-dipole",
        )
        self.assertEqual(recommendation.verdict, "try this pass")
        self.assertEqual(recommendation.difficulty, "good")

    def test_scan_json_runs_without_hardware_probe(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            status = cli.main(["scan", "--json"])
        self.assertEqual(status, 0)
        self.assertIn('"name": "rtl_test"', buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
