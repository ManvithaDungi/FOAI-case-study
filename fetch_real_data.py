"""Fetch Phase II trial statistics from the ClinicalTrials.gov API v2 (public, no key needed).

Usage:  python fetch_real_data.py [--pages 10]
Writes: data/phase2_trials.csv and data/phase2_summary.json
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics as st
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

API = "https://clinicaltrials.gov/api/v2/studies"
DATA = Path(__file__).parent / "data"


def get(params: dict) -> dict:
    url = API + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "foai-case-study"}), timeout=60) as r:
        return json.load(r)


def months(start: str | None, end: str | None) -> float | None:
    def parse(s):
        parts = [int(x) for x in s.split("-")]
        return date(parts[0], parts[1], parts[2] if len(parts) > 2 else 1)
    if not start or not end:
        return None
    d = (parse(end) - parse(start)).days / 30.44
    return round(d, 1) if d > 0 else None


def row(study: dict) -> dict:
    p = study.get("protocolSection", {})
    ident, design = p.get("identificationModule", {}), p.get("designModule", {})
    status, arms = p.get("statusModule", {}), p.get("armsInterventionsModule", {})
    elig, loc = p.get("eligibilityModule", {}), p.get("contactsLocationsModule", {})
    return {
        "nct_id": ident.get("nctId"),
        "enrollment": (design.get("enrollmentInfo") or {}).get("count"),
        "duration_months": months((status.get("startDateStruct") or {}).get("date"),
                                  (status.get("completionDateStruct") or {}).get("date")),
        "arms": len(arms.get("armGroups") or []),
        "sites": len(loc.get("locations") or []),
        "std_ages": "|".join(elig.get("stdAges") or []),
        "conditions": "|".join((p.get("conditionsModule") or {}).get("conditions") or [])[:120],
    }


def summarise(rows: list[dict], label: str) -> dict:
    def stats(key, lo=0):
        v = [r[key] for r in rows if isinstance(r[key], (int, float)) and r[key] > lo]
        if not v:
            return None
        q = st.quantiles(v, n=4) if len(v) > 3 else [v[0]] * 3
        return {"n": len(v), "median": st.median(v), "q1": q[0], "q3": q[2], "mean": round(st.mean(v), 1)}
    return {"subset": label, "trials": len(rows), "enrollment": stats("enrollment"),
            "duration_months": stats("duration_months"), "arms": stats("arms"), "sites": stats("sites")}


def fetch(pages: int) -> list[dict]:
    params = {"query.term": "AREA[Phase]PHASE2 AND AREA[StudyType]INTERVENTIONAL",
              "filter.overallStatus": "COMPLETED", "pageSize": 1000, "format": "json",
              "fields": "NCTId|EnrollmentInfo|StartDate|CompletionDate|ArmGroup|LocationFacility|StdAge|Condition"}
    out, token = [], None
    for _ in range(pages):
        if token:
            params["pageToken"] = token
        data = get(params)
        out += [row(s) for s in data.get("studies", [])]
        token = data.get("nextPageToken")
        print(f"  fetched {len(out)} studies", flush=True)
        if not token:
            break
        time.sleep(0.5)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=5, help="pages of 1000 studies")
    rows = fetch(ap.parse_args().pages)
    DATA.mkdir(exist_ok=True)
    with open(DATA / "phase2_trials.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    summary = {"source": "ClinicalTrials.gov API v2", "accessed": date.today().isoformat(),
               "filter": "Phase 2, interventional, completed",
               "all": summarise(rows, "all Phase II"),
               "pediatric": summarise([r for r in rows if "CHILD" in r["std_ages"].split("|")
                                       and "ADULT" not in r["std_ages"].split("|")], "children only"),
               "adult": summarise([r for r in rows if "ADULT" in r["std_ages"].split("|")], "includes adults")}
    (DATA / "phase2_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
