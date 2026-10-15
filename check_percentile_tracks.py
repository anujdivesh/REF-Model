"""List cyclone tracks that have data in any MEAN_WIND_*_PERCENTILE column.

Usage:
    python check_percentile_tracks.py [output.csv]
"""
import csv
import json
import re
import sys
import urllib.request

URL = "https://pacific-disaster-api.spc.int/partner_api/v1/cyclone_track/?format=json"
PERCENTILE_RE = re.compile(r"^MEAN_WIND_\d+_PERCENTILE$")


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


def percentile_columns_with_data(track):
    cols = set()
    features = (track.get("geometry") or {}).get("features", [])
    for feature in features:
        for key, value in (feature.get("properties") or {}).items():
            if PERCENTILE_RE.match(key) and value not in (None, ""):
                cols.add(key)
    return cols


def main():
    out_csv = sys.argv[1] if len(sys.argv) > 1 else "tracks_with_percentiles.csv"
    tracks = fetch_tracks(URL)
    print(f"Fetched {len(tracks)} tracks")

    rows = []
    for track in tracks:
        cols = percentile_columns_with_data(track)
        if cols:
            rows.append({
                "id": track.get("id"),
                "cyclone_name": track.get("cyclone_name"),
                "percentile_columns": ";".join(sorted(cols)),
            })

    print(f"\nTracks with MEAN_WIND_*_PERCENTILE data: {len(rows)}")
    for row in rows:
        print(f"  {row['id']}\t{row['cyclone_name']}\t{row['percentile_columns']}")

    with open(out_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "cyclone_name", "percentile_columns"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nWrote {out_csv}")


if __name__ == "__main__":
    main()
