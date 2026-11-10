import datetime as dt
import unittest
from pycpt_tutorial.cpt_dates import normalize_initialization_dates


class CptInitializationTests(unittest.TestCase):
    def test_date_only_midnight_is_allowed_only_for_audited_dates(self):
        raw="cpt:S=2020-11-01, cpt:T=2020-12/2021-02\n1.25\t35.0\n"
        result,dates=normalize_initialization_dates(raw,[dt.datetime(2020,11,1)])
        self.assertEqual(result,"cpt:S=2020-11-01T00:00, cpt:T=2020-12/2021-02\n1.25\t35.0\n")
        self.assertEqual(dates,["2020-11-01"])

    def test_timestamp_and_numerical_data_are_retained(self):
        raw="cpt:S=2020-11-01T00:00, cpt:T=2020-12/2021-02\n-999\t20.1\n"
        self.assertEqual(normalize_initialization_dates(raw,[dt.datetime(2020,11,1)]),(raw,[]))

    def test_unknown_date_cannot_be_silently_repaired(self):
        with self.assertRaises(ValueError):
            normalize_initialization_dates("cpt:S=2019-11-01, cpt:T=2020-12",[dt.datetime(2020,11,1)])

    def test_non_midnight_initializations_cannot_be_assumed(self):
        with self.assertRaises(ValueError):
            normalize_initialization_dates("cpt:S=2020-11-01, cpt:T=2020-12",[dt.datetime(2020,11,1,12)])

    def test_initialization_at_end_of_header_line_is_normalized(self):
        source="cpt:C=1, cpt:S=2020-11-01\n12.5\t87.5\n"
        normalized,dates=normalize_initialization_dates(source,[dt.datetime(2020,11,1)])
        self.assertEqual(normalized,"cpt:C=1, cpt:S=2020-11-01T00:00\n12.5\t87.5\n")
        self.assertEqual(dates,["2020-11-01"])


if __name__=="__main__": unittest.main()
