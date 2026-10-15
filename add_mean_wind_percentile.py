"""Add a MEAN_WIND_10_PERCENTILE column (copy of MeanWind) to track CSVs.

The model's FMS-Track-GeoJSON bookmark reads MEAN_WIND_10_PERCENTILE, while
the FMS upload CSVs only have MeanWind. Edits files in place; files that
already have the column are skipped.

Usage:
    python add_mean_wind_percentile.py              # all CSVs in new/
    python add_mean_wind_percentile.py a.csv b.csv  # specific files
"""
import csv
import glob
import sys

DEFAULT_GLOB = "new/*.csv"
NEW_COL = "MEAN_WIND_10_PERCENTILE"
SRC_COL = "MeanWind"


def add_column(path):
    with open(path, newline="") as f:
        lines = f.read().splitlines()

    heading_idx = next(i for i, l in enumerate(lines) if l.startswith("Time["))
    names = next(csv.reader([lines[heading_idx]]))
    if NEW_COL in names:
        return "already has column, skipped"
    src = names.index(SRC_COL)

    out = []
    for i, line in enumerate(lines):
        if i == heading_idx:
            out.append(f"{line},{NEW_COL}")
        elif line.startswith("(Time->("):
            out.append(line.replace("))", f",{NEW_COL}))", 1))
        elif line.startswith("#"):
            out.append(line + ",")  # keep comment lines padded to full width
        elif i > heading_idx and line.strip():
            cells = next(csv.reader([line]))
            out.append(f"{line},{cells[src]}")
        else:
            out.append(line)

    with open(path, "w", newline="") as f:
        f.write("\n".join(out) + "\n")
    return f"added {NEW_COL} from {SRC_COL}"


def main():
    paths = sys.argv[1:] or sorted(glob.glob(DEFAULT_GLOB))
    for path in paths:
        print(f"{path}: {add_column(path)}")


if __name__ == "__main__":
    main()
