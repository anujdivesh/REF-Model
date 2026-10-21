"""Convert longitudes over 180 to the -180..180 range (subtract 360) in a
track CSV, writing <name>_fixed.csv.

Only the Longitude column of data rows is changed; header and comment lines
are copied as-is.

Usage:
    python fix_longitude.py new/Harold_20200401T000000Z_TO.csv
"""
import csv
import os
import sys


def fix(path):
    with open(path, newline="") as f:
        lines = f.read().splitlines()

    heading_idx = next(i for i, l in enumerate(lines) if l.startswith("Time"))
    lon_idx = next(csv.reader([lines[heading_idx]])).index("Longitude")

    changed = 0
    out = lines[:heading_idx + 1]
    for line in lines[heading_idx + 1:]:
        if not line.strip() or line.startswith("#"):
            out.append(line)
            continue
        cells = next(csv.reader([line]))
        lon = float(cells[lon_idx])
        if lon > 180:
            cells[lon_idx] = f"{lon - 360:g}"
            changed += 1
            line = ",".join(cells)
        out.append(line)

    root, ext = os.path.splitext(path)
    out_path = f"{root}_fixed{ext}"
    with open(out_path, "w", newline="") as f:
        f.write("\n".join(out) + "\n")
    print(f"{path} -> {out_path}  ({changed} longitudes changed)")


if __name__ == "__main__":
    for p in sys.argv[1:]:
        fix(p)
