"""Scientific guardrails for input preparation, without any fitter or network."""
import unittest
import numpy as np
import xarray as xr
from pycpt_tutorial.subseasonal_inputs import (
    week_bounds,week_dates,expected_leads,gefs_weekly,chirps_weekly)

class SubseasonalInputTests(unittest.TestCase):
    def raw(self,kind='hindcast'):
        members=11 if kind=='hindcast' else 31
        units='kg m-2' if kind=='hindcast' else 'kg m-2 s-1'
        data=np.ones((1,members,21,2,2),dtype=float)
        if kind=='forecast':data/=86400
        ds=xr.Dataset({'pr':(('S','M','L','Y','X'),data)},coords={
            'S':[np.datetime64('2018-08-29','ns')],'M':np.arange(members),
            'L':np.arange(7.5,28),'Y':[-1,1],'X':[100,101]})
        ds.pr.attrs['units']=units;ds.L.attrs['units']='days'
        return ds

    def observation(self):
        mass=np.zeros((76,192));mass[0,0]=4
        grid=xr.Dataset({'native_weight':('point',[1.,3.]),'coarse_index':('point',[0,0]),
            'country_land_weight':(('latitude','longitude'),mass)},
            coords={'point':[0,1],'latitude':np.arange(76),'longitude':np.arange(192)},attrs={'grid_id':'test'})
        dates=np.arange(np.datetime64('2018-09-05'),np.datetime64('2018-09-26')).astype('datetime64[ns]')
        daily=xr.Dataset({'rainfall_amount':(('time','point'),np.tile([10.,20.],(21,1)))},
            coords={'time':dates,'point':[0,1]},attrs={'grid_id':'test'})
        daily.rainfall_amount.attrs['units']='mm'
        return daily,grid

    def test_year_boundary_and_exclusive_end(self):
        a,b=week_bounds('2019-12-25',2)
        self.assertEqual(a,np.datetime64('2020-01-01'))
        self.assertEqual(b,np.datetime64('2020-01-08'))
        self.assertEqual(len(week_dates('2019-12-25',2)),7)

    def test_leap_day_included(self):
        dates=week_dates('2020-02-19',2)
        self.assertIn(np.datetime64('2020-02-29'),dates)
        self.assertEqual(len(dates),7)

    def test_midnight_and_supported_weeks_required(self):
        with self.assertRaises(ValueError):week_bounds('2023-08-24T06:00:00Z',2)
        with self.assertRaises(ValueError):week_bounds('2023-08-24T00:00:00+07:00',2)
        with self.assertRaises(ValueError):week_bounds('2023-08-24',1)

    def test_hindcast_amount_and_forecast_rate_agree(self):
        h=gefs_weekly(self.raw(),'hindcast','2018-08-29')
        f=gefs_weekly(self.raw('forecast'),'forecast','2018-08-29')
        np.testing.assert_allclose(h.rainfall_amount,7,atol=1e-12)
        np.testing.assert_allclose(f.rainfall_amount,7,atol=1e-12)
        self.assertEqual(str(h.target_start[0,0].values)[:10],'2018-09-05')
        self.assertEqual(h.daily_count.attrs['units'],'1')
        self.assertEqual(h.member_count.attrs['units'],'1')

    def test_one_day_shift_detectable(self):
        d=self.raw();d['pr']=d.pr*d.L
        d.pr.attrs['units']='kg m-2'
        result=gefs_weekly(d,'hindcast','2018-08-29')
        self.assertEqual(float(result.rainfall_amount[0,0,0,0,0]),73.5)
        self.assertEqual(expected_leads(4).tolist(),[21.5,22.5,23.5,24.5,25.5,26.5,27.5])

    def test_missing_member_day_or_value_rejected(self):
        for changed in [self.raw().isel(M=slice(0,10)),self.raw().isel(L=slice(1,None))]:
            with self.assertRaises(ValueError):gefs_weekly(changed,'hindcast','2018-08-29')
        d=self.raw();d.pr.values[0,0,0,0,0]=np.nan
        with self.assertRaises(ValueError):gefs_weekly(d,'hindcast','2018-08-29')

    def test_unknown_units_negative_and_wrong_date_rejected(self):
        d=self.raw();d.pr.attrs['units']='mm/day'
        with self.assertRaises(ValueError):gefs_weekly(d,'hindcast','2018-08-29')
        d=self.raw();d.pr.values[0,0,0,0,0]=-1
        with self.assertRaises(ValueError):gefs_weekly(d,'hindcast','2018-08-29')
        with self.assertRaises(ValueError):gefs_weekly(self.raw(),'hindcast','2018-08-30')

    def test_observations_time_sum_then_area_average(self):
        daily,grid=self.observation()
        out=chirps_weekly(daily,grid,'2018-08-29','rnl')
        np.testing.assert_allclose(out.rainfall_amount.values[0,:,0,0],122.5)
        self.assertTrue(np.isnan(out.rainfall_amount.values[0,0,0,1]))

    def test_observation_missing_days_and_duplicates_rejected(self):
        daily,grid=self.observation()
        with self.assertRaises(ValueError):chirps_weekly(daily.isel(time=slice(1,None)),grid,'2018-08-29','rnl')
        duplicate=xr.concat([daily,daily.isel(time=[0])],dim='time')
        with self.assertRaises(ValueError):chirps_weekly(duplicate,grid,'2018-08-29','rnl')

    def test_missing_pixels_never_become_dry_zero(self):
        daily,grid=self.observation();daily.rainfall_amount.values[0,1]=np.nan
        out=chirps_weekly(daily,grid,'2018-08-29','rnl')
        self.assertTrue(np.isnan(out.rainfall_amount.values[0,0,0,0]))
        self.assertEqual(float(out.country_coverage_fraction.values[0,0,0,0]),.25)
        daily.rainfall_amount.values[:]=0
        out=chirps_weekly(daily,grid,'2018-08-29','rnl')
        self.assertEqual(float(out.rainfall_amount.values[0,0,0,0]),0)

if __name__=='__main__':unittest.main()
