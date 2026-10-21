"""Check whether track CSVs have everything the model needs to run.

The model reads tracks through [bookmark FMS-Track-GeoJSON], which uses the
API (UPPER_SNAKE) column names. For each CSV this checks:

  * every column the bookmark reads is present (RiskScape fails otherwise)
  * LATITUDE, LONGITUDE and TIME have a value on every row
  * MEAN_WIND_10_PERCENTILE has data (otherwise every point gets 0 wind)

CSV names are matched to API names ignoring case and non-alphanumerics, so
NEGaleRadius counts as NE_GALE_RADIUS, but MeanWind does NOT count as
MEAN_WIND_10_PERCENTILE (the API is the source of truth).

Writes model_ready.csv: one row per bookmark column, one column per file.

Usage:
    python check_model_ready.py              # all CSVs in new/
    python check_model_ready.py a.csv b.csv  # specific files
"""
import csv
import glob
import os
import re
import sys

from check_track_columns import BOOKMARK_COLUMNS

DEFAULT_GLOB = "new/*.csv"
OUT_CSV = "model_ready.csv"

# Must have a value on every row
FULL_DATA = ["LATITUDE", "LONGITUDE", "TIME"]
# Must have a value on at least one row
SOME_DATA = ["MEAN_WIND_10_PERCENTILE"]


def key(name):
    return re.sub(r"[^A-Z0-9]", "", name.upper())


def has_value(value):
    return value is not None and value.strip() not in ("", "NaN", "nan")


def read_csv(path):
    """Return (column names, rows as dicts) from a track CSV."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        lines = [l.rstrip("\r\n") for l in f]
    idx = next((i for i, l in enumerate(lines) if l.startswith("Time")), 0)
    # Some files separate header names with tabs or pad with blank cells
    names = [c.strip() for c in next(csv.reader([lines[idx].replace("\t", ",")])) if c.strip()]
    names[0] = re.sub(r"\[.*\]$", "", names[0])  # Time[fmt=...] -> Time

    rows = []
    for line in lines[idx + 1:]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        cells = [c.strip() for c in next(csv.reader([line]))]
        rows.append(dict(zip(names, cells)))
    return names, rows


def check_file(path):
    """Return ({bookmark column: status text}, ready, [reasons not ready])."""
    names, rows = read_csv(path)
    by_key = {key(n): n for n in names}
    status, problems = {}, []

    for col in BOOKMARK_COLUMNS:
        src = by_key.get(key(col))
        if src is None:
            status[col] = "MISSING"
            problems.append(f"{col} missing")
            continue
        count = sum(1 for r in rows if has_value(r.get(src)))
        status[col] = f"{src} ({count}/{len(rows)})"
        if col in FULL_DATA and count < len(rows):
            status[col] += " INCOMPLETE"
            problems.append(f"{col} empty on {len(rows) - count} rows")
        elif col in SOME_DATA and count == 0:
            status[col] += " NO DATA"
            problems.append(f"{col} has no data")
        elif count == 0:
            status[col] += " no data (defaults)"
    return status, not problems, problems


def main():
    paths = sys.argv[1:] or sorted(glob.glob(DEFAULT_GLOB))
    if not paths:
        sys.exit(f"No CSVs found ({DEFAULT_GLOB})")

    names = [os.path.basename(p) for p in paths]
    results = {name: check_file(p) for name, p in zip(names, paths)}

    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["model_column"] + names)
        writer.writerow(["READY"] + ["YES" if results[n][1] else "NO" for n in names])
        for col in BOOKMARK_COLUMNS:
            writer.writerow([col] + [results[n][0][col] for n in names])

    for name in names:
        _, ready, problems = results[name]
        print(f"{name}: {'READY' if ready else 'NOT READY'}")
        for p in problems:
            print(f"    - {p}")
    print(f"\nWrote {OUT_CSV}")


if __name__ == "__main__":
    main()
