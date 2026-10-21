"""Convert a cyclone track from the SPC API to the FMS forecast CSV format.

The '#' header block and column list are taken from an existing FMS CSV
(the template); baseTime is set from the API track's issued_time. Values are
written as the API has them, except:
  * Time: "yyyy-MM-dd HH:mm:ss" -> "yyyy-MM-ddTHH:mm:ssZ"
  * Longitude: negative values -> 0..360, as in FMS files
  * missing/null values -> NaN
Columns the API doesn't have are written as NaN and reported.

Usage:
    python api_to_fms_csv.py 150 new/20261018T120000Z_Official_Forecast_Track_2627_01F_Wati.csv
Output: <template name>_api<id>.csv next to the template
"""
import csv
import json
import os
import re
import sys
import urllib.request
from datetime import datetime

API_URL = "https://pacific-disaster-api.spc.int/partner_api/v1/cyclone_track/{id}/?format=json"


def fetch(track_id):
    with urllib.request.urlopen(API_URL.format(id=track_id), timeout=60) as resp:
        return json.load(resp)


def iso(value):
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            pass
    raise ValueError(f"Unrecognised time: {value!r}")


def cell(column, value):
    if value is None or value == "":
        return "NaN"
    if column == "Longitude" and float(value) < 0:
        return f"{float(value) + 360:g}"
    return str(value)


def main():
    if len(sys.argv) != 3:
        sys.exit("Usage: python api_to_fms_csv.py <track id> <template.csv>")
    track_id, template = sys.argv[1], sys.argv[2]

    with open(template, newline="") as f:
        lines = f.read().splitlines()
    heading_idx = next(i for i, l in enumerate(lines) if l.startswith("Time["))
    columns = next(csv.reader([lines[heading_idx]]))[1:]
    end = next(i for i, l in enumerate(lines) if l.startswith("# Start of data"))
    header = lines[:end + 1]

    track = fetch(track_id)
    base = iso(track["issued_time"].replace("T", " ").rstrip("Z"))
    header[0] = re.sub(r"baseTime=[^,]*", f"baseTime={base}", header[0])

    props = [f["properties"] for f in track["geometry"]["features"]]
    available = set().union(*[p.keys() for p in props])
    missing = [c for c in columns if c not in available]

    out = list(header)
    for p in props:
        out.append(",".join([iso(p["Time"])] + [cell(c, p.get(c)) for c in columns]))

    out_path = f"{os.path.splitext(template)[0]}_api{track_id}.csv"
    with open(out_path, "w", newline="") as f:
        f.write("\n".join(out) + "\n")

    print(f"Track {track_id} ({track.get('cyclone_name')}, issued {track['issued_time']})")
    print(f"  -> {out_path}  ({len(props)} points)")
    if missing:
        print(f"  not in API (written as NaN): {', '.join(missing)}")


if __name__ == "__main__":
    main()
