"""Real-data reference for the scenarios: Phase II trials from ClinicalTrials.gov.

The scenario starting values (320 / 220 / 180 patients, 10 hospitals, 18 months) are kept from the
case-study report; `validation()` shows where each sits in the real distribution.

`data/phase2_trials.csv` is produced by `fetch_real_data.py`. If the file is absent the
hard-coded fallbacks (the values measured on 2026-10-14) are used so the project still runs.
"""

from __future__ import annotations

import csv
import statistics
from functools import lru_cache
from pathlib import Path

CSV_PATH = Path(__file__).parent / "data" / "phase2_trials.csv"

# Measured on 5,000 completed Phase II interventional trials, accessed 2026-10-14.
FALLBACK = {
    "n_trials": 5000,
    "enroll_p80": 150, "enroll_p90": 260, "enroll_p95": 405,
    "multisite_median_sites": 9,
    "child_enroll_p85": 320, "child_multisite_median_sites": 8,
    "median_arms": 2, "duration_q1": 16, "duration_median": 32,
}


def _pct(values: list[float], p: float) -> float:
    v = sorted(values)
    return v[min(len(v) - 1, int(p / 100 * len(v)))]


def _round(x: float, base: int) -> int:
    return int(round(x / base) * base)


@lru_cache(maxsize=1)
def calibration() -> dict:
    """Return the calibration values plus provenance."""
    if not CSV_PATH.exists():
        return {**FALLBACK, "source": "fallback constants (ClinicalTrials.gov, accessed 2026-10-14)"}
    with open(CSV_PATH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    def col(key: str, keep=lambda r: True, min_value: float = 0) -> list[float]:
        return [float(r[key]) for r in rows if r[key] and float(r[key]) > min_value and keep(r)]

    child = lambda r: "CHILD" in r["std_ages"] and "ADULT" not in r["std_ages"]
    enroll, c_enroll = col("enrollment"), col("enrollment", child)
    return {
        "n_trials": len(rows),
        "enroll_p80": _round(_pct(enroll, 80), 5),
        "enroll_p90": _round(_pct(enroll, 90), 5),
        "enroll_p95": _round(_pct(enroll, 95), 5),
        "multisite_median_sites": round(statistics.median(col("sites", min_value=1))),
        "child_enroll_p85": _round(_pct(c_enroll, 85), 10),
        "child_multisite_median_sites": round(statistics.median(col("sites", child, min_value=1))),
        "median_arms": round(statistics.median(col("arms"))),
        "duration_q1": round(_pct(col("duration_months"), 25)),
        "duration_median": round(statistics.median(col("duration_months"))),
        "source": f"ClinicalTrials.gov API v2, {len(rows)} completed Phase II trials (data/phase2_trials.csv)",
    }


# Percentile ranks measured on the same 5,000 trials (used if the CSV is missing).
_FALLBACK_RANKS = {"sample_size": 92.4, "sponsor_cap": 87.7, "sponsor_target": 83.5, "hospitals": 54.3,
                   "duration_months": 29.4}


def _rank(values: list[float], x: float) -> float:
    return round(100 * sum(1 for v in values if v <= x) / len(values), 1)


@lru_cache(maxsize=1)
def validation() -> dict:
    """Percentile of the baseline starting values within real completed Phase II trials."""
    if not CSV_PATH.exists():
        return {"percentile_ranks": dict(_FALLBACK_RANKS), "n_trials": FALLBACK["n_trials"]}
    with open(CSV_PATH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    def col(key: str, min_value: float = 0) -> list[float]:
        return [float(r[key]) for r in rows if r[key] and float(r[key]) > min_value]

    enroll, sites, dur = col("enrollment"), col("sites", 1), col("duration_months")
    return {"n_trials": len(rows), "percentile_ranks": {
        "sample_size": _rank(enroll, 320), "sponsor_cap": _rank(enroll, 220), "sponsor_target": _rank(enroll, 180),
        "hospitals": _rank(sites, 10), "duration_months": _rank(dur, 18)}}
