"""Explicit ending-year calendars for rolling three-month rainfall seasons."""
from dataclasses import dataclass
import calendar
import datetime as dt

SEASONS=("DJF","JFM","FMA","MAM","AMJ","MJJ","JJA","JAS","ASO","SON","OND","NDJ")
START_MONTH={name:month for name,month in zip(SEASONS,(12,1,2,3,4,5,6,7,8,9,10,11))}


@dataclass(frozen=True)
class SeasonWindow:
    season: str
    year: int
    initialization: dt.datetime
    start: dt.datetime
    end: dt.datetime
    months: tuple
    days: tuple


def season_window(season,year):
    """Label NDJ/DJF by their ending year; issue one month before target start."""
    if season not in START_MONTH:
        raise ValueError(f"Unknown season: {season}")
    if type(year) is not int or not 1900<=year<=2200:
        raise ValueError("year must be an integer in1900–2200")
    month=START_MONTH[season]
    start_year=year-1 if month in (11,12) else year
    starts=[]
    for offset in range(3):
        serial=start_year*12+month-1+offset
        starts.append(dt.datetime(serial//12,serial%12+1,1))
    days=tuple(calendar.monthrange(value.year,value.month)[1] for value in starts)
    end=starts[-1].replace(day=days[-1])
    initial_serial=start_year*12+month-2
    initialization=dt.datetime(initial_serial//12,initial_serial%12+1,1)
    assert end.year==year
    return SeasonWindow(season,year,initialization,starts[0],end,tuple(starts),days)
