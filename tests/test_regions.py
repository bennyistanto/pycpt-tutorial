import unittest
import numpy as np
import xarray as xr
from pycpt_tutorial.regions import score_regions, pool_years


class RegionalScores(unittest.TestCase):
    def setUp(self):
        self.obs=xr.DataArray([[0.,0.]],dims=("Y","X"),coords={"Y":[0],"X":[1,2]})
        self.forecast=self.obs+xr.DataArray([[2.,6.]],dims=("Y","X"))
        self.weights=xr.DataArray([[[3.,1.]],[[1.,3.]]],dims=("region","Y","X"),coords={"region":["A","B"],"Y":[0],"X":[1,2]})

    def test_shared_coarse_cells_conserve_national_mse(self):
        result=score_regions(self.forecast,self.obs,self.weights)
        np.testing.assert_allclose(result.mse,[12.,28.])
        np.testing.assert_allclose(result.mae,[3.,5.])
        self.assertAlmostEqual(float((result.mse*.5).sum()),20.)
        self.assertNotAlmostEqual(float(result.rmse.mean()),np.sqrt(20.),places=5)

    def test_pooling_uses_mse_before_square_root(self):
        annual=xr.Dataset({"mse":("season_year",[1.,9.]),"mae":("season_year",[1.,3.]),"bias":("season_year",[-1.,3.])})
        result=pool_years(annual)
        self.assertAlmostEqual(float(result.rmse),np.sqrt(5.))
        self.assertAlmostEqual(float(result.bias),1.)

    def test_missing_weighted_values_are_rejected(self):
        bad=self.forecast.copy(); bad.values[0,1]=np.nan
        with self.assertRaises(ValueError): score_regions(bad,self.obs,self.weights)

    def test_empty_region_and_negative_weights_rejected(self):
        for value in (0.,-1.):
            bad=self.weights.copy(); bad.loc[dict(region="A")]=value
            with self.assertRaises(ValueError): score_regions(self.forecast,self.obs,bad)

    def test_different_grid_is_not_silently_aligned(self):
        with self.assertRaises(ValueError): score_regions(self.forecast.assign_coords(X=[1,3]),self.obs,self.weights)


if __name__=="__main__": unittest.main()
