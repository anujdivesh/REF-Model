"""Convert reprojected track CSVs (EPSG:3857 / EPSG:3832 metres) back to
lat/lon degrees (EPSG:4326), e.g. for plotting on a Leaflet map.

Reads <name>_<epsg>.csv (from reproject.py) and writes <name>_<epsg>_latlon.csv
with the same layout; only the Latitude/Longitude columns change.

Longitudes are kept continuous (consecutive points never jump by more than
180 degrees, e.g. 179 -> 181 rather than 179 -> -179), so Pacific tracks that
cross the dateline draw as one line in Leaflet.

Usage:
    python unproject.py new/Meena_20050201T000000Z_CK_3832.csv [more.csv ...]
"""
import csv
import math
import os
import re
import sys

from reproject import A, CRS, E


def inverse_mercator(x, y, lon0, ellipsoidal):
    lon = lon0 + math.degrees(x / A)
    t = math.exp(-y / A)
    phi = math.pi / 2 - 2 * math.atan(t)
    if ellipsoidal:
        for _ in range(15):  # converges in a few iterations
            es = E * math.sin(phi)
            phi = math.pi / 2 - 2 * math.atan(t * ((1 - es) / (1 + es)) ** (E / 2))
    return math.degrees(phi), lon


def unproject(path):
    m = re.search(r"_(\d{4})\.csv$", path)
    if not m or m.group(1) not in CRS:
        sys.exit(f"{path}: name must end in _<epsg>.csv with epsg in {list(CRS)}")
    epsg = m.group(1)
    lon0, ellipsoidal, _, _ = CRS[epsg]

    with open(path, newline="") as f:
        lines = f.read().splitlines()
    heading_idx = next(i for i, l in enumerate(lines) if l.startswith("Time"))
    names = next(csv.reader([lines[heading_idx]]))
    lat_i, lon_i = names.index("Latitude"), names.index("Longitude")

    out = lines[:heading_idx + 1]
    prev_lon = None
    for line in lines[heading_idx + 1:]:
        if not line.strip() or line.startswith("#"):
            out.append(line)
            continue
        cells = next(csv.reader([line]))
        lat, lon = inverse_mercator(float(cells[lon_i]), float(cells[lat_i]), lon0, ellipsoidal)
        if prev_lon is None:
            lon %= 360  # Pacific tracks sit naturally in 0..360
        else:
            lon += 360 * round((prev_lon - lon) / 360)  # stay within 180 of previous
        prev_lon = lon
        cells[lat_i], cells[lon_i] = f"{lat:.5f}", f"{lon:.5f}"
        out.append(",".join(cells))

    out_path = path[:-len(".csv")] + "_latlon.csv"
    with open(out_path, "w", newline="") as f:
        f.write("\n".join(out) + "\n")
    print(f"{path} -> {out_path}  (EPSG:{epsg} -> EPSG:4326 degrees)")


if __name__ == "__main__":
    for p in sys.argv[1:]:
        unproject(p)
