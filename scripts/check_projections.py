"""Print the coordinate system / longitude convention of track CSVs.

CSVs carry no CRS of their own: Latitude/Longitude are degrees, which the
model's bookmark reads as EPSG:4326 (WGS84). A .prj sidecar, if present, is
reported instead. For each file this prints the lat/lon ranges, whether
longitudes are 0..360, -180..180 or mixed, and whether the track crosses
the 180 degree meridian.

Usage:
    python check_projections.py              # all CSVs in new/
    python check_projections.py a.csv b.csv  # specific files
"""
import csv
import glob
import os
import sys

DEFAULT_GLOB = "new/*.csv"


def read_coords(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        lines = [l.rstrip("\r\n") for l in f]
    idx = next(i for i, l in enumerate(lines) if l.startswith("Time"))
    names = [c.strip() for c in next(csv.reader([lines[idx].replace("\t", ",")]))]
    lat_i, lon_i = names.index("Latitude"), names.index("Longitude")

    coords = []
    for line in lines[idx + 1:]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        cells = next(csv.reader([line]))
        coords.append((float(cells[lat_i]), float(cells[lon_i])))
    return coords


def crs_of(path):
    prj = os.path.splitext(path)[0] + ".prj"
    if os.path.exists(prj):
        with open(prj) as f:
            return f"{f.read().strip()[:80]} (from .prj)"
    return "EPSG:4326 WGS84 lat/lon degrees (assumed, no CRS in CSV)"


def lon_convention(lons):
    if any(l > 180 for l in lons) and any(l < 0 for l in lons):
        return "MIXED (has both >180 and negative values)"
    if any(l > 180 for l in lons):
        return "0..360"
    if any(l < 0 for l in lons):
        return "-180..180"
    return "0..180 (valid in both conventions)"


def crosses_dateline(lons):
    """True if consecutive points step across the 180 meridian."""
    norm = [l % 360 for l in lons]  # 0..360 so the dateline is at 180
    return any((a <= 180) != (b <= 180) and abs(a - b) < 180
               for a, b in zip(norm, norm[1:]))


def main():
    paths = sys.argv[1:] or sorted(glob.glob(DEFAULT_GLOB))
    for path in paths:
        coords = read_coords(path)
        lats = [c[0] for c in coords]
        lons = [c[1] for c in coords]
        bad = [c for c in coords if not (-90 <= c[0] <= 90 and -180 <= c[1] <= 360)]

        print(f"=== {os.path.basename(path)}  ({len(coords)} points)")
        print(f"  CRS:            {crs_of(path)}")
        print(f"  Longitude:      {lon_convention(lons)}")
        print(f"  Latitude range: {min(lats):g} to {max(lats):g}")
        print(f"  Longitude range:{min(lons):g} to {max(lons):g}")
        print(f"  Crosses 180:    {'yes' if crosses_dateline(lons) else 'no'}")
        if bad:
            print(f"  OUT OF RANGE:   {len(bad)} points, e.g. {bad[0]}")


if __name__ == "__main__":
    main()
