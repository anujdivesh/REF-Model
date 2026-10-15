"""Compare the columns of track CSVs against the columns in the SPC API.

The API is the source of truth: writes csv_vs_api_columns.csv with one row
per API column and, for each CSV file, the matching column name or MISSING.
CSV columns with no API equivalent are listed at the end as "(not in API)".
Only column names are checked, not data.

API names are UPPER_SNAKE (NE_GALE_RADIUS) and CSV names are CamelCase
(NEGaleRadius), so names are matched ignoring case and non-alphanumerics.

Usage:
    python check_csv_vs_api_columns.py              # all CSVs in new/
    python check_csv_vs_api_columns.py a.csv b.csv  # specific files
    python check_csv_vs_api_columns.py --track 61   # use track 61 as reference
"""
import csv
import glob
import json
import os
import re
import sys
import urllib.request

API_URL = "https://pacific-disaster-api.spc.int/partner_api/v1/cyclone_track/?format=json"
DEFAULT_GLOB = "new/*.csv"
OUT_CSV = "csv_vs_api_columns.csv"


def fetch_tracks(url):
    tracks = []
    while url:
        with urllib.request.urlopen(url, timeout=60) as resp:
            data = json.load(resp)
        # Handle both a plain list and a DRF paginated response
        if isinstance(data, dict):
            tracks.extend(data.get("results", []))
            url = data.get("next")
        else:
            tracks.extend(data)
            url = None
    return tracks


def track_columns(track):
    """GeoJSON property names of one track, in first-seen order."""
    cols = {}
    for feature in (track.get("geometry") or {}).get("features", []):
        for key in feature.get("properties") or {}:
            cols.setdefault(key, None)
    return list(cols)


def reference_track(tracks, track_id=None):
    """The track whose columns define the API schema.

    The API also holds a few older uploads in the CamelCase file format, so
    don't take the union of all tracks: use the requested track, or else the
    most recently issued track that has data.
    """
    if track_id is not None:
        return next(t for t in tracks if str(t["id"]) == str(track_id))
    with_data = [t for t in tracks if track_columns(t)]
    return max(with_data, key=lambda t: t.get("issued_time") or "")


def csv_columns(path):
    """Column names from the 'Time[...]' heading row (or the first row)."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        lines = [l.rstrip("\r\n") for l in f]
    header = next((l for l in lines if l.startswith("Time")), lines[0])
    # Some files separate names with tabs or pad with blank cells
    cells = next(csv.reader([header.replace("\t", ",")]))
    names = [c.strip() for c in cells if c.strip()]
    names[0] = re.sub(r"\[.*\]$", "", names[0])  # Time[fmt=...] -> Time
    return names


def key(name):
    return re.sub(r"[^A-Z0-9]", "", name.upper())


def main():
    args = sys.argv[1:]
    track_id = None
    if "--track" in args:
        i = args.index("--track")
        track_id = args[i + 1]
        del args[i:i + 2]
    paths = args or sorted(glob.glob(DEFAULT_GLOB))
    if not paths:
        sys.exit(f"No CSVs found ({DEFAULT_GLOB})")

    tracks = fetch_tracks(API_URL)
    ref = reference_track(tracks, track_id)
    api = track_columns(ref)
    print(f"API reference: track {ref['id']} ({ref.get('cyclone_name')}, "
          f"issued {ref.get('issued_time')}) - {len(api)} columns")

    # One row per API column; per file, the matching CSV column or MISSING
    names = [os.path.basename(p) for p in paths]
    by_key = {name: {key(c): c for c in csv_columns(p)} for name, p in zip(names, paths)}
    api_keys = {key(c) for c in api}

    rows = []
    for col in api:
        row = {"api_column": col}
        for name in names:
            row[name] = by_key[name].get(key(col), "MISSING")
        rows.append(row)
    # CSV columns with no API equivalent, listed after the API columns
    extra_keys = {}
    for name in names:
        for k in by_key[name]:
            if k not in api_keys:
                extra_keys.setdefault(k, None)
    for k in extra_keys:
        row = {"api_column": "(not in API)"}
        for name in names:
            row[name] = by_key[name].get(k, "")
        rows.append(row)

    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["api_column"] + names)
        writer.writeheader()
        writer.writerows(rows)

    for name in names:
        missing = sum(1 for r in rows if r[name] == "MISSING")
        print(f"  {name}: {len(api) - missing} matched, {missing} missing")
    print(f"\nWrote {OUT_CSV}")


if __name__ == "__main__":
    main()
