"""Tests for pycpt_tutorial.checks, using the real Fit & diagnose OND inputs."""
from pathlib import Path
import datetime as dt
import tempfile
import unittest

import xarray as xr

from pycpt_tutorial import checks

DATA = Path(__file__).resolve().parents[1] / "docs/data/fitting-2023"
ARGS = {
    "fdate": dt.datetime(2023, 9, 1), "target": "Oct-Dec",
    "target_first_year": 1991, "target_final_year": 2020,
    "predictor_extent": {"west": 85, "east": 155, "south": -20, "north": 20},
    "predictand_extent": {"west": 94, "east": 142, "south": -12, "north": 7},
}


def load(name):
    with xr.open_dataset(DATA / name) as ds:
        return ds.precipitation.load()


class ChecksOnRealInputs(unittest.TestCase):
    def setUp(self):
        self.Y = load("OND-Y.nc")
        self.X = load("OND-X.nc")
        self.F = load("OND-F.nc")

    def status(self, table, check):
        return table.set_index("check").loc[check, "status"]

    def test_case_two_observations_carry_s_and_are_flagged(self):
        # The Fit & diagnose observation file was built with the model's S coordinate.
        self.assertIn("S", self.Y.coords)
        rows = {r["check"]: r["status"] for r in checks.check_predictand(self.Y, "CHIRPS3.PRCP")}
        self.assertEqual(rows["predictand has no initialization date"], "fail")
        self.assertEqual(rows["predictand attributes"], "ok")

    def test_clean_observations_pass(self):
        clean = self.Y.drop_vars("S")
        rows = {r["check"]: r["status"] for r in checks.check_predictand(clean, "CHIRPS3.PRCP")}
        self.assertEqual(set(rows.values()), {"ok"})

    def test_missing_attribute_and_name(self):
        bad = self.Y.drop_vars("S")
        bad.attrs = {k: v for k, v in bad.attrs.items() if k != "missing"}
        rows = {r["check"]: r["status"] for r in checks.check_predictand(bad, "CHIRPS3 (local)")}
        self.assertEqual(rows["predictand attributes"], "fail")
        self.assertEqual(rows["predictand name"], "warn")

    def test_full_case_and_missing_years(self):
        Y = self.Y.drop_vars("S")
        table = checks.check_case(ARGS, "CHIRPS3.PRCP", Y, [self.X], [self.F], ["CFSv2.PRCP"])
        self.assertNotIn("fail", set(table["status"]))
        short = self.X.isel(T=slice(2, None))
        table = checks.check_case(ARGS, "CHIRPS3.PRCP", Y, [short], [None], ["CFSv2.PRCP"])
        self.assertEqual(self.status(table, "CFSv2.PRCP: hindcast years"), "fail")
        self.assertEqual(self.status(table, "CFSv2.PRCP: dates match observations"), "fail")
        self.assertEqual(self.status(table, "CFSv2.PRCP: forecast"), "fail")

    def test_question_record(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(checks.check_question(ARGS, folder)["status"], "warn")
            checks.remember_question(ARGS, folder)
            self.assertEqual(checks.check_question(ARGS, folder)["status"], "ok")
            changed = dict(ARGS, target="Dec-Feb")
            result = checks.check_question(changed, folder)
            self.assertEqual(result["status"], "fail")
            self.assertIn("target", result["detail"])


if __name__ == "__main__":
    unittest.main()
