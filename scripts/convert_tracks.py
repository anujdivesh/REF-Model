"""Convert cyclone track CSVs to the FMS upload format used in uploads/.

Output name: <CycloneName>_<IssuedTime>_<CountryCode>.csv

Handles the input variations seen so far:
  * header names separated by ",," or ",<tab>" (blank / padded columns)
  * no "# ..." metadata block at all
  * "yyyy-MM-dd HH:mm:ss" timestamps (converted to yyyy-MM-ddTHH:mm:ssZ)
  * empty cells (written as NaN)
  * negative longitudes (converted to 0-360, as in the FMS upload files)

Usage:
    python convert_tracks.py
"""
import csv
import os
import re
from datetime import datetime

OUT_DIR = "new"

COLUMNS = [
    "Latitude", "Longitude", "Symbol", "Category", "Pressure", "PressureOCI", "RadiusOCI",
    "Radius1000hPa", "RadiusMaxWinds", "MeanWind", "WindGust", "VerticalExtent", "Uncertainty",
    "FinalT", "CurrentIntensity", "GaleRadius", "StrongGaleRadius", "StormRadius",
    "HurricaneRadius", "NEGaleRadius", "SEGaleRadius", "SWGaleRadius", "NWGaleRadius",
    "NEStrongGaleRadius", "SEStrongGaleRadius", "SWStrongGaleRadius", "NWStrongGaleRadius",
    "NEStormRadius", "SEStormRadius", "SWStormRadius", "NWStormRadius", "NEHurricaneRadius",
    "SEHurricaneRadius", "SWHurricaneRadius", "NWHurricaneRadius", "P5Wind", "DataSource",
    "Land/Water", "CycloneStatus", "HowLocation", "DataTNoDvorak", "ModelTNoDvorak",
    "PatternTNoDvorak", "UncPressure", "HowPressure", "P/W_Method", "HowMaxWindRadius",
    "HowGaleRadius", "HowStormRadius", "HowHurricaneRadius", "UncMaxWindSpeed",
    "HowMaxWindSpeed", "HowGust", "EyeRadius", "UncEyeRadius", "HowEyeRadius",
]
TIME_HEADER = "Time[fmt=yyyy-MM-dd'T'HH:mm:ss'Z']"
PAD = "," * len(COLUMNS)  # comment lines are padded to the full column count

# source file -> (cyclone name, track type, country code)
TRACKS = {
    "check/20050201T000000Z_GP_Analysis_Track_XXXX_XXF_MEENA_v2.csv": ("Meena", "GP Analysis Track", "CK"),
    "check/20200401T000000Z_GP_Analysis_Track_XXXX_XXF_HAROLD.csv": ("Harold", "GP Analysis Track", "TO"),
    "check/Official_Forecast_Track_GITA_SA.csv": ("Gita", "Official Forecast Track", "WS"),
}


def split(line):
    return [cell.strip() for cell in next(csv.reader([line]))]


def read_track(path):
    """Return a list of {column: value} dicts, one per data row."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        lines = [l.rstrip("\r\n") for l in f]

    header_idx = next(i for i, l in enumerate(lines) if l.startswith("Time["))
    # Header may contain blank padding cells between names, and some names are
    # separated only by a tab (no comma); data rows have neither
    header = split(lines[header_idx].replace("\t", ","))
    names = [h for h in header if h]
    names[0] = "Time"

    rows = []
    for line in lines[header_idx + 1:]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        cells = split(line)
        if len(cells) < len(names):
            cells += [""] * (len(names) - len(cells))
        rows.append(dict(zip(names, cells)))
    return names, rows


def norm_time(value):
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    raise ValueError(f"Unrecognised time: {value!r}")


def norm_value(column, value):
    if value in ("", "nan", "NaN", "NAN"):
        return "NaN"
    if column == "Longitude":
        lon = float(value)
        if lon < 0:
            return f"{lon + 360:g}"
    return value


def issued_time(path, first_time):
    m = re.match(r"(\d{8}T\d{6}Z)", os.path.basename(path))
    return datetime.strptime(m.group(1), "%Y%m%dT%H%M%SZ") if m else first_time


def convert(path, name, track_type, country):
    names, rows = read_track(path)
    unknown = [n for n in names[1:] if n not in COLUMNS]
    if unknown:
        raise ValueError(f"{path}: unknown columns {unknown}")
    missing = [c for c in COLUMNS if c not in names]

    times = [norm_time(r["Time"]) for r in rows]
    issued = issued_time(path, times[0])
    stamp = issued.strftime("%Y%m%dT%H%M%SZ")

    out_lines = [
        f"# trackType={track_type},baseTime={issued:%Y-%m-%dT%H:%M:%SZ}" + PAD[1:],
        "# DisturbanceId=" + PAD,
        f"# CycloneName={name}" + PAD,
        "# MathType of Data" + PAD,
        "(Time->(" + ",".join(COLUMNS) + ")),",
        "# Column Headings" + PAD,
        ",".join([TIME_HEADER] + COLUMNS),
        "# Start of data" + PAD,
    ]
    for t, row in zip(times, rows):
        values = [norm_value(c, row.get(c, "")) for c in COLUMNS]
        out_lines.append(",".join([f"{t:%Y-%m-%dT%H:%M:%SZ}"] + values))

    out_path = os.path.join(OUT_DIR, f"{name}_{stamp}_{country}.csv")
    with open(out_path, "w", newline="") as f:
        f.write("\n".join(out_lines) + "\n")

    print(f"{path}\n  -> {out_path}  ({len(rows)} rows)")
    if missing:
        print(f"  columns not in source (filled with NaN): {', '.join(missing)}")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for path, (name, track_type, country) in TRACKS.items():
        convert(path, name, track_type, country)


if __name__ == "__main__":
    main()
