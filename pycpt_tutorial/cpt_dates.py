"""Scoped normalization of verified midnight initializations in CPT output text."""
from contextlib import contextmanager
import datetime as dt
import hashlib
import importlib
from pathlib import Path
import re

DATE_ONLY=re.compile(r"(cpt:S=)(\d{4}-\d{2}-\d{2})(?=,|\s|$)")


def normalize_initialization_dates(text,expected):
    """Represent date-only S values as midnight, only for independently known dates.

    cptio1.4.0's read_cpt_date requires'T' in a timestamp. CPT17.8.3 can emit
    YYYY-MM-DD initialization fields in multi-forecast output. No target dates,
    probabilities or numerical values are modified.
    """
    if any(value.time()!=dt.time(0,0) for value in expected):
        raise ValueError("Date-only repair requires independently verified midnight initializations")
    allowed={value.date().isoformat() for value in expected}
    dates=[]
    def replace(match):
        value=match.group(2)
        if value not in allowed:
            raise ValueError(f"CPT initialization{value} was not in the audited input calendar")
        dt.date.fromisoformat(value)
        dates.append(value)
        return match.group(1)+value+"T00:00"
    return DATE_ONLY.sub(replace,text),dates


@contextmanager
def verified_midnight_reader(function,expected):
    """Temporarily wrap this cptcore function's reader; retain raw and parsing copies."""
    module=importlib.import_module(function.__module__)
    original=module.open_cptdataset
    events=[]
    def reader(filename,*args,**kwargs):
        source=Path(filename)
        text=source.read_text()
        normalized,dates=normalize_initialization_dates(text,expected)
        if not dates: return original(filename,*args,**kwargs)
        parsing=source.with_name(source.stem+".midnight-normalized"+source.suffix)
        parsing.write_text(normalized)
        events.append({"source":str(source),"parsing_copy":str(parsing),"dates":dates,
                       "source_sha256":hashlib.sha256(source.read_bytes()).hexdigest(),"parsing_sha256":hashlib.sha256(parsing.read_bytes()).hexdigest()})
        return original(str(parsing),*args,**kwargs)
    module.open_cptdataset=reader
    try: yield events
    finally: module.open_cptdataset=original
