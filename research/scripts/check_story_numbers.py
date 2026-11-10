"""Check that the numbers typed into the lead-time story tables equal the notebooks' saved CSVs.

Each table cell must equal the CSV value rounded to the decimals shown. Writes
research/audits/lead-time/story-numbers.json and exits non-zero on any mismatch.

    python research/scripts/check_story_numbers.py
"""
from pathlib import Path
import json
import re
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
STORIES = {
    "monthly-leads-2023": {
        "skill": ("data/monthly-2023/skill-by-lead.csv", "| Lead | CCA Pearson |",
                  [("CCA", "Pearson"), ("PCR", "Pearson"), ("raw CFSv2", "Pearson"), ("CCA", "2AFC (%)"), ("PCR", "2AFC (%)")]),
        "2023": ("data/monthly-2023/november-2023-forecasts.csv", "| Lead | Method | Hit rate (%) |",
                 ["hit rate (%)", "RPSS 2023", "RMSE 2023 (mm)", "mean forecast (mm)"]),
    },
    "seasonal-leads-2023": {
        "skill": ("data/ond-leads-2023/skill-by-lead.csv", "| Lead | CCA Pearson |",
                  [("CCA", "Pearson"), ("PCR", "Pearson"), ("raw CFSv2", "Pearson"), ("CCA", "2AFC (%)"), ("PCR", "2AFC (%)")]),
        "2023": ("data/ond-leads-2023/ond-2023-forecasts.csv", "| Lead | Method | Hit rate (%) |",
                 ["hit rate (%)", "RPSS 2023", "RMSE 2023 (mm)", "mean forecast (mm)"]),
        "comparison": ("data/ond-leads-2023/seasonal-vs-monthly.csv", "| Lead | CCA, OND |",
                       [("CCA", "Pearson, OND"), ("CCA", "Pearson, November"), ("raw CFSv2", "Pearson, OND"), ("raw CFSv2", "Pearson, November")]),
    },
    "dekad-leads-2023": {
        "skill": ("data/dekad-leads-2023/skill-by-lead.csv", "| Lead | CCA Pearson |",
                  [("CCA", "Pearson"), ("PCR", "Pearson"), ("raw GEFS", "Pearson"), ("CCA", "2AFC (%)"),
                   ("CCA", "ROC below normal"), ("CCA", "ROC above normal")]),
        "2023": ("data/dekad-leads-2023/ond-2023-dekad-forecasts.csv", "| Lead | Method | Hit rate (%) |",
                 ["hit rate (%)", "RPSS 2023", "RMSE 2023 (mm)", "forecast below (%)"]),
    },
}


def table_rows(text, header):
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith(header))
    rows = []
    for line in lines[start + 2:]:
        if not line.startswith("|"):
            break
        rows.append([c.strip() for c in line.strip("|").split("|")])
    return rows


def matches(shown, value):
    decimals = len(shown.split(".")[1]) if "." in shown else 0
    return abs(float(shown) - value) <= 0.5 * 10 ** -decimals + 1e-9


report, bad = {}, 0
for page, tables in STORIES.items():
    text = (DOCS / "chapters" / f"{page}.qmd").read_text(encoding="utf-8")
    for name, (csv, header, columns) in tables.items():
        data = pd.read_csv(DOCS / csv).set_index(["lead", "method"])
        checked = mismatches = 0
        for row in table_rows(text, header):
            lead = int(re.match(r"(\d+)", row[0]).group(1))
            if isinstance(columns[0], tuple):
                pairs = [((lead, m), c) for m, c in columns]
                cells = row[1:]
            else:
                method = row[1].upper() if row[1] in ("CCA", "PCR") else row[1]
                pairs = [((lead, method), c) for c in columns]
                cells = row[2:]
            for (key, column), shown in zip(pairs, cells):
                value = float(data.loc[key, column])
                checked += 1
                if not matches(shown, value):
                    mismatches += 1
                    print(f"MISMATCH {page} {name} {key} {column}: page {shown}, CSV {value}")
        report[f"{page}/{name}"] = {"cells checked": checked, "mismatches": mismatches}
        bad += mismatches
out = ROOT / "research/audits/lead-time/story-numbers.json"
out.write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
sys.exit(1 if bad else 0)
