from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout

from pmgs import cli
from pmgs.capture import CapturePlan, rtl_sdr_command
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
