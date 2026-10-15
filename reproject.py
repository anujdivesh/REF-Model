"""Reproject track CSVs from EPSG:4326 (lat/lon degrees) to a projected CRS,
writing <name>_<epsg>.csv plus a .prj sidecar.

Supported targets:
    3857  WGS 84 / Pseudo-Mercator (spherical, central meridian 0)
    3832  WGS 84 / PDC Mercator    (ellipsoidal, central meridian 150E;
                                    keeps Pacific tracks continuous over 180)

Longitudes may be 0..360 or -180..180. The file layout and column names are
kept, so after reprojection:
    Longitude column = X (easting, metres)
    Latitude column  = Y (northing, metres)

Usage:
    python reproject.py 3832 new/Meena_20050201T000000Z_CK.csv [more.csv ...]
"""
import csv
import math
import os
import sys

A = 6378137.0                # WGS84 semi-major axis
F = 1 / 298.257223563        # WGS84 flattening
E = math.sqrt(F * (2 - F))   # WGS84 eccentricity

GEOGCS = ('GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],'
          'PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]]')


def prj(name, central_meridian, epsg):
    return (f'PROJCS["{name}",{GEOGCS},PROJECTION["Mercator_1SP"],'
            f'PARAMETER["central_meridian",{central_meridian}],PARAMETER["scale_factor",1],'
            'PARAMETER["false_easting",0],PARAMETER["false_northing",0],'
            f'UNIT["metre",1],AUTHORITY["EPSG","{epsg}"]]')


# epsg -> (central meridian, ellipsoidal?, max latitude, .prj WKT)
CRS = {
    "3857": (0.0, False, 85.05112878, prj("WGS 84 / Pseudo-Mercator", 0, 3857)),
    "3832": (150.0, True, 89.0, prj("WGS 84 / PDC Mercator", 150, 3832)),
}


def mercator(lat, lon, lon0, ellipsoidal, max_lat):
    dlon = (lon - lon0 + 180.0) % 360.0 - 180.0  # wrap around the central meridian
    phi = math.radians(max(-max_lat, min(max_lat, lat)))
    x = A * math.radians(dlon)
    y = math.log(math.tan(math.pi / 4 + phi / 2))
    if ellipsoidal:
        es = E * math.sin(phi)
        y += (E / 2) * math.log((1 - es) / (1 + es))
    return x, A * y


def reproject(epsg, path):
    lon0, ellipsoidal, max_lat, wkt = CRS[epsg]
    with open(path, newline="") as f:
        lines = f.read().splitlines()

    heading_idx = next(i for i, l in enumerate(lines) if l.startswith("Time"))
    names = next(csv.reader([lines[heading_idx]]))
    lat_i, lon_i = names.index("Latitude"), names.index("Longitude")

    out = lines[:heading_idx + 1]
    count = 0
    for line in lines[heading_idx + 1:]:
        if not line.strip() or line.startswith("#"):
            out.append(line)
            continue
        cells = next(csv.reader([line]))
        x, y = mercator(float(cells[lat_i]), float(cells[lon_i]), lon0, ellipsoidal, max_lat)
        cells[lon_i], cells[lat_i] = f"{x:.2f}", f"{y:.2f}"
        out.append(",".join(cells))
        count += 1

    root, ext = os.path.splitext(path)
    out_path = f"{root}_{epsg}{ext}"
    with open(out_path, "w", newline="") as f:
        f.write("\n".join(out) + "\n")
    with open(f"{root}_{epsg}.prj", "w") as f:
        f.write(wkt)
    print(f"{path} -> {out_path}  ({count} points, EPSG:{epsg} metres)")


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in CRS:
        sys.exit(f"Usage: python reproject.py {{{'|'.join(CRS)}}} file.csv [...]")
    for path in sys.argv[2:]:
        reproject(sys.argv[1], path)


if __name__ == "__main__":
    main()
