"""Calendar contracts before expanding to overlapping/year-crossing targets."""
import datetime as dt
import unittest
from pycpt_tutorial.seasons import SEASONS, season_window


class SeasonCalendarTests(unittest.TestCase):
    def test_cross_year_targets_use_ending_year(self):
        djf=season_window("DJF",2022)
        self.assertEqual((djf.initialization,djf.start,djf.end),(dt.datetime(2021,11,1),dt.datetime(2021,12,1),dt.datetime(2022,2,28)))
        ndj=season_window("NDJ",2022)
        self.assertEqual((ndj.initialization,ndj.start,ndj.end),(dt.datetime(2021,10,1),dt.datetime(2021,11,1),dt.datetime(2022,1,31)))

    def test_january_start_has_previous_year_initialization(self):
        self.assertEqual(season_window("JFM",2021).initialization,dt.datetime(2020,12,1))

    def test_real_leap_days_change_accumulation(self):
        self.assertEqual(sum(season_window("DJF",2024).days),91)
        self.assertEqual(sum(season_window("DJF",2023).days),90)
        self.assertEqual(sum(season_window("FMA",2024).days),90)
        self.assertEqual(sum(season_window("FMA",2023).days),89)

    def test_all_twelve_windows_have_three_adjacent_months(self):
        for season in SEASONS:
            window=season_window(season,2024)
            serial=[value.year*12+value.month for value in window.months]
            self.assertEqual([serial[1]-serial[0],serial[2]-serial[1]],[1,1])
            self.assertEqual(window.end.year,2024)
            first=window.start.year*12+window.start.month
            issued=window.initialization.year*12+window.initialization.month
            self.assertEqual(first-issued,1)

    def test_earliest_common_training_year_needs_no1981_initializations(self):
        self.assertTrue(all(season_window(name,1983).initialization>=dt.datetime(1982,1,1) for name in SEASONS))
        self.assertEqual([name for name in SEASONS if season_window(name,1982).initialization<dt.datetime(1982,1,1)],["DJF","JFM","NDJ"])


if __name__=="__main__": unittest.main()
