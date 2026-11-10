"""Scientific aggregation contracts: country-only means and no holdout fitting."""
import unittest
import numpy as np
import xarray as xr
from pycpt_tutorial.country_grid import aggregate_country_rainfall, training_complete_mask


class CountryGridTests(unittest.TestCase):
    def field(self,values):
        return xr.DataArray(values,dims=("lat","lon"),coords={"lat":[-1.5,-.5,.5,1.5],"lon":[100.5,101.5,102.5,103.5]})

    def test_foreign_or_ocean_values_cannot_contaminate_country_mean(self):
        values=self.field(np.full((4,4),10000.)); values.values[:2,:2]=12.
        mask=self.field(np.zeros((4,4),bool)); mask.values[:2,:2]=True
        actual=aggregate_country_rainfall(values,mask,4)
        self.assertAlmostEqual(actual.precipitation.item(),12.)

    def test_missing_coverage_and_zero_rain_are_distinct(self):
        values=self.field(np.zeros((4,4))); mask=xr.ones_like(values,dtype=bool)
        self.assertEqual(aggregate_country_rainfall(values,mask,4).precipitation.item(),0.)
        values.values[0,0]=np.nan
        self.assertTrue(bool(aggregate_country_rainfall(values,mask,4).precipitation.isnull()))

    def test_weighted_fine_to_coarse_matches_direct_aggregation(self):
        values=self.field(np.arange(16,dtype=float).reshape(4,4))
        mask=xr.ones_like(values,dtype=bool); mask.values[0,0]=False
        fine=aggregate_country_rainfall(values,mask,2)
        recombined=(fine.precipitation*fine.country_land_weight).sum()/fine.country_land_weight.sum()
        direct=aggregate_country_rainfall(values,mask,4).precipitation.squeeze()
        np.testing.assert_allclose(recombined,direct,atol=1e-12)

    def test_verification_missingness_cannot_fit_training_mask(self):
        data=xr.DataArray([[1.,2.],[2.,3.],[np.nan,4.]],dims=("T","X"),coords={"T":np.array(["1982-11-15","1983-11-15","2023-11-15"],dtype="datetime64[ns]")})
        np.testing.assert_array_equal(training_complete_mask(data,[1982,1983]),[True,True])


if __name__=="__main__": unittest.main()
