"""Check that a cyclone track from the SPC API has the columns used by the
RiskScape [bookmark FMS-Track-GeoJSON].

Reports which columns are missing from the API, how many points have data
in each column that exists, and the attributes the bookmark would derive.

Usage:
    python check_track_columns.py [track_id]      # default: 61
"""
import json
import sys
import urllib.request

API_URL = "https://pacific-disaster-api.spc.int/partner_api/v1/cyclone_track/{id}/?format=json"
MAXFLOAT = sys.float_info.max

GALE = ["NE_GALE_RADIUS", "NW_GALE_RADIUS", "SE_GALE_RADIUS", "SW_GALE_RADIUS", "GALE_RADIUS"]
STORM = ["NE_STORM_RADIUS", "NW_STORM_RADIUS", "SE_STORM_RADIUS", "SW_STORM_RADIUS", "STORM_RADIUS"]
HURRICANE = ["NE_HURRICANE_RADIUS", "NW_HURRICANE_RADIUS", "SE_HURRICANE_RADIUS",
             "SW_HURRICANE_RADIUS", "HURRICANE_RADIUS"]

# Columns read by [bookmark FMS-Track-GeoJSON], in the order they are used
BOOKMARK_COLUMNS = [
    "LATITUDE", "LONGITUDE",                # geom
    "TIME",                                 # Time
    "RADIUS_MAX_WINDS",                     # RadiusMaxWinds
    "MEAN_WIND_10_PERCENTILE",              # MeanWind
    *GALE,                                  # Min/MaxGaleRadius
    *STORM,                                 # Min/MaxStormRadius
    *HURRICANE,                             # Min/MaxHurricaneRadius
    "UNCERTAINTY",                          # Uncertainty
]


def fetch_track(track_id):
    with urllib.request.urlopen(API_URL.format(id=track_id), timeout=60) as resp:
        return json.load(resp)


def is_not_null(value):
    return value is not None and str(value).strip() != ""


def or_default(value, default):
    return float(value) if is_not_null(value) else default


def derive(props):
    """Mirror the set-attribute expressions of the bookmark."""
    lon = float(props["LONGITUDE"])
    return {
        "Lat": float(props["LATITUDE"]),
        "Lon": lon if lon <= 180.0 else lon - 360.0,
        "TIME": props["TIME"],
        "RadiusMaxWinds": or_default(props.get("RADIUS_MAX_WINDS"), 0.0),
        "MeanWind": or_default(props.get("MEAN_WIND_10_PERCENTILE"), 0.0),
        "MinGaleRadius": min(or_default(props.get(c), MAXFLOAT) for c in GALE),
        "MaxGaleRadius": max(or_default(props.get(c), 0.0) for c in GALE),
        "MinStormRadius": min(or_default(props.get(c), MAXFLOAT) for c in STORM),
        "MaxStormRadius": max(or_default(props.get(c), 0.0) for c in STORM),
        "MinHurricaneRadius": min(or_default(props.get(c), MAXFLOAT) for c in HURRICANE),
        "MaxHurricaneRadius": max(or_default(props.get(c), 0.0) for c in HURRICANE),
        "Uncertainty": or_default(props.get("UNCERTAINTY"), 0.0),
    }


def fmt(value):
    if isinstance(value, float):
        return "maxfloat" if value == MAXFLOAT else f"{value:g}"
    return str(value)


def main():
    track_id = sys.argv[1] if len(sys.argv) > 1 else "61"
    track = fetch_track(track_id)
    features = (track.get("geometry") or {}).get("features", [])
    rows = [feature.get("properties") or {} for feature in features]

    print(f"Track {track['id']}: {track.get('cyclone_name')}  ({len(rows)} points)")

    available = set()
    for row in rows:
        available.update(row.keys())
    missing = [c for c in BOOKMARK_COLUMNS if c not in available]
    present = [c for c in BOOKMARK_COLUMNS if c in available]

    print(f"\nColumns used by FMS-Track-GeoJSON: {len(BOOKMARK_COLUMNS)}  |  "
          f"present: {len(present)}  |  missing: {len(missing)}")

    print("\nMissing columns (not in API):")
    for col in missing or ["(none)"]:
        print(f"  - {col}")

    print("\nPresent columns (points with data / total):")
    for col in present:
        count = sum(1 for row in rows if is_not_null(row.get(col)))
        flag = "" if count else "   <-- all null"
        print(f"  {col:<26} {count:>3}/{len(rows)}{flag}")

    if missing:
        print("\nSkipping derived attributes: bookmark would fail on missing columns")
        return

    print("\nDerived attributes (as the bookmark computes them):")
    derived = [derive(row) for row in rows]
    headers = list(derived[0].keys())
    widths = {h: max(len(h), *(len(fmt(d[h])) for d in derived)) for h in headers}
    print("  " + "  ".join(h.rjust(widths[h]) for h in headers))
    for d in derived:
        print("  " + "  ".join(fmt(d[h]).rjust(widths[h]) for h in headers))


if __name__ == "__main__":
    main()
