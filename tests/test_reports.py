from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pmgs.reports import Observation, load_observation, render_html_report, write_report


class ReportTests(unittest.TestCase):
    def test_render_report_escapes_html(self) -> None:
        observation = Observation(
            satellite="<METEOR>",
            pass_time="2026-06-11T22:18:00-05:00",
            max_elevation=64.0,
            frequency_mhz=137.9,
            device="RTL-SDR",
            antenna="stock dipole",
            location_note="window",
            artifacts=["capture<1>.iq"],
        )
        html = render_html_report(observation)
        self.assertIn("&lt;METEOR&gt;", html)
        self.assertIn("capture&lt;1&gt;.iq", html)

    def test_load_and_write_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "observation.json"
            output = root / "report.html"
            source.write_text(
                json.dumps(
                    {
                        "satellite": "METEOR-M N2-4",
                        "pass_time": "2026-06-11T22:18:00-05:00",
                        "max_elevation": 64,
                        "frequency_mhz": 137.9,
                        "device": "RTL-SDR Blog V4",
                        "antenna": "stock dipole",
                        "location_note": "indoor window",
                    }
                ),
                encoding="utf-8",
            )
            observation = load_observation(source)
            write_report(observation, output)
            self.assertTrue(output.exists())
            self.assertIn("METEOR-M N2-4", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
