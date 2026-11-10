"""Exercise NetCDF data integrity and file replacement behavior in Debian."""
from pathlib import Path
import tempfile
import unittest

import netCDF4
import numpy as np
import xarray as xr

from pycpt_tutorial.export import save_netcdf


class NetCDFExportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.target = Path(self.directory.name) / "results.nc"
        self.dataset = xr.Dataset(
            {"rain": (("T", "Y", "X"), [[[100.0, np.nan], [200.0, 300.0]]])},
            coords={
                "T": np.array(["2020-11-15"], dtype="datetime64[ns]"),
                "Ti": ("T", np.array(["2020-10-01"], dtype="datetime64[ns]")),
                "Tf": ("T", np.array(["2020-12-31"], dtype="datetime64[ns]")),
                "S": ("T", np.array(["2020-09-01"], dtype="datetime64[ns]")),
                "Y": [-7.0, -8.0], "X": [111.0, 112.0],
            },
            attrs={"source_kind": "synthetic"},
        )
        self.dataset.rain.attrs = {"units": "mm", "missing": -999.0}

    def test_data_missing_values_dates_units_and_metadata_survive(self):
        save_netcdf(self.dataset, self.target, metadata={"method": "CCA"})
        expected = self.dataset.assign_attrs(method="CCA")
        with xr.open_dataset(self.target) as reopened:
            xr.testing.assert_identical(expected, reopened.load())
        self.assertNotIn("method", self.dataset.attrs)
        with netCDF4.Dataset(self.target) as stored:
            self.assertTrue(stored.variables["rain"].filters()["zlib"])
        self.assertEqual(list(self.target.parent.glob(".results-*.nc")), [])

    def test_extra_model_lead_and_category_dimensions_survive(self):
        values = np.broadcast_to(np.array([20., 30., 50.]), (2, 2, 3)).copy()
        dataset = xr.Dataset(
            {"probability": (("model", "lead_name", "C"), values)},
            coords={"model": ["model_a", "model_b"], "lead_name": ["week_1", "week_2"], "C": [1, 2, 3]},
        )
        dataset.probability.attrs["units"] = "probability (%)"
        save_netcdf(dataset, self.target)
        with xr.open_dataset(self.target) as reopened:
            xr.testing.assert_identical(dataset, reopened.load())
            np.testing.assert_allclose(reopened.probability.sum("C"), 100.)

    def test_named_dataarray_can_be_saved(self):
        save_netcdf(self.dataset.rain, self.target)
        with xr.open_dataset(self.target) as reopened:
            xr.testing.assert_identical(self.dataset.rain, reopened.rain.load())
        with self.assertRaises(ValueError):
            save_netcdf(self.dataset.rain.rename(None), self.target.parent / "unnamed.nc")

    def test_zero_compression_overrides_existing_compression_encoding(self):
        self.dataset.rain.encoding.update(zlib=True, complevel=9)
        save_netcdf(self.dataset, self.target, compression=0)
        with netCDF4.Dataset(self.target) as stored:
            self.assertFalse(stored.variables["rain"].filters()["zlib"])
        with xr.open_dataset(self.target) as reopened:
            xr.testing.assert_identical(self.dataset, reopened.load())

    def test_overwrite_requires_explicit_opt_in(self):
        self.target.write_bytes(b"keep existing output")
        with self.assertRaises(FileExistsError):
            save_netcdf(self.dataset, self.target)
        self.assertEqual(self.target.read_bytes(), b"keep existing output")
        save_netcdf(self.dataset, self.target, overwrite=True)
        with xr.open_dataset(self.target) as reopened:
            xr.testing.assert_identical(self.dataset, reopened.load())

    def test_failed_export_does_not_replace_an_existing_result(self):
        self.target.write_bytes(b"keep existing output")
        with self.assertRaises((TypeError, ValueError)):
            save_netcdf(self.dataset, self.target, metadata={"invalid": {"nested": "object"}}, overwrite=True)
        self.assertEqual(self.target.read_bytes(), b"keep existing output")
        self.assertEqual(list(self.target.parent.glob(".results-*.nc")), [])


if __name__ == "__main__":
    unittest.main()
