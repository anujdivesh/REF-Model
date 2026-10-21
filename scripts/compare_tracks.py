"""Compare two cyclone tracks from the SPC API, to see why one gives model
results and the other doesn't.

Reports:
  * columns that differ (missing, or with data in one track only)
  * time format and longitude convention
  * wind radii per band (the model's wind swaths are built from these)
  * closest approach to islands in the model's countries (VU, WS, CK, TO)
    and whether each island falls inside the gale radius

Usage:
    python compare_tracks.py 74 131
"""
import json
import math
import sys
import urllib.request

API_URL = "https://pacific-disaster-api.spc.int/partner_api/v1/cyclone_track/{id}/?format=json"
NM_TO_KM = 1.852

# Approximate island locations for the countries the model has exposure for
ISLANDS = {
    "VU": {"Efate": (-17.73, 168.32), "Espiritu Santo": (-15.30, 167.00),
           "Malekula": (-16.20, 167.50), "Tanna": (-19.50, 169.30)},
    "WS": {"Upolu": (-13.83, -171.76), "Savai'i": (-13.65, -172.45)},
    "CK": {"Rarotonga": (-21.23, -159.78), "Aitutaki": (-18.86, -159.79),
           "Atiu": (-19.99, -158.12), "Mitiaro": (-19.87, -157.71),
           "Mauke": (-20.16, -157.34), "Mangaia": (-21.92, -157.93),
           "Manihiki": (-10.43, -161.00), "Rakahanga": (-10.03, -161.09),
           "Penrhyn": (-9.01, -158.05), "Pukapuka": (-10.88, -165.85)},
    "TO": {"Tongatapu": (-21.15, -175.20), "Ha'apai": (-19.80, -174.35),
           "Vava'u": (-18.65, -173.98), "Niuatoputapu": (-15.96, -173.78)},
}

GALE = ["NEGaleRadius", "SEGaleRadius", "SWGaleRadius", "NWGaleRadius"]
STORM = ["NEStormRadius", "SEStormRadius", "SWStormRadius", "NWStormRadius"]
HURRICANE = ["NEHurricaneRadius", "SEHurricaneRadius", "SWHurricaneRadius", "NWHurricaneRadius"]
WIND = ["MEAN_WIND", "MeanWind", "MEAN_WIND_10_PERCENTILE", "WIND_SPD", "WindGust", "P5Wind"]


def fetch(track_id):
    with urllib.request.urlopen(API_URL.format(id=track_id), timeout=60) as resp:
        return json.load(resp)


def points(track):
    return [f["properties"] for f in (track.get("geometry") or {}).get("features", [])]


def has(v):
    return v not in (None, "", "NaN")


def num(v):
    return float(v) if has(v) else None


def haversine(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 6371 * math.asin(math.sqrt(h))


def densify(pts, steps=20):
    """Points along the track, interpolating between fixes (lon unwrapped)."""
    out = []
    for p, q in zip(pts, pts[1:]):
        dlon = (q[1] - p[1] + 180) % 360 - 180
        for i in range(steps):
            t = i / steps
            out.append((p[0] + t * (q[0] - p[0]), p[1] + t * dlon, p, q, t))
    out.append((*pts[-1], pts[-1], pts[-1], 0))
    return out


def max_gale_km(props):
    vals = [num(props.get(c)) for c in GALE + ["GaleRadius"]]
    vals = [v for v in vals if v is not None]
    return max(vals) * NM_TO_KM if vals else 0.0


def column_report(ps_a, ps_b, a, b):
    cols = sorted(set().union(*[p.keys() for p in ps_a + ps_b]))
    print(f"\n--- Columns that differ ({a} vs {b}; points with data / total, '-' = no column)")
    print(f"  {'column':30} {a:>8} {b:>8}")
    for c in cols:
        cells = []
        for ps in (ps_a, ps_b):
            if not any(c in p for p in ps):
                cells.append("-")
            else:
                cells.append(f"{sum(1 for p in ps if has(p.get(c)))}/{len(ps)}")
        # only show differences that matter: presence or data/no-data
        state = [x if x == "-" else ("data" if not x.startswith("0/") else "empty") for x in cells]
        if state[0] != state[1]:
            print(f"  {c:30} {cells[0]:>8} {cells[1]:>8}")


def track_report(tid, track, ps):
    print(f"\n=== Track {tid}: {track.get('cyclone_name')}  ({len(ps)} points)")
    times = [p.get("Time") for p in ps]
    lons = [num(p.get("Longitude")) for p in ps]
    print(f"  Time format:   {times[0]!r}")
    conv = "0..360" if any(l > 180 for l in lons) else "-180..180"
    print(f"  Longitude:     {conv} ({min(lons):g} to {max(lons):g})")

    for name, cols in (("Gale (34kt)", GALE), ("Storm (48kt)", STORM), ("Hurricane (64kt)", HURRICANE)):
        n = sum(1 for p in ps if any(has(p.get(c)) for c in cols))
        print(f"  {name:17} radii on {n}/{len(ps)} points")
    for c in WIND:
        vals = [num(p.get(c)) for p in ps if has(p.get(c))]
        if vals:
            print(f"  {c:17} {min(vals):g} to {max(vals):g}")
        elif any(c in p for p in ps):
            print(f"  {c:17} column present, no data")

    pts = [(num(p["Latitude"]), num(p["Longitude"])) for p in ps]
    track_line = densify(pts)
    print("  Closest approach to model countries (gale radius at that point):")
    for country, islands in ISLANDS.items():
        best = None
        for island, loc in islands.items():
            d, i = min((haversine(loc, s[:2]), k) for k, s in enumerate(track_line))
            if best is None or d < best[0]:
                best = (d, island, i)
        d, island, i = best
        # gale radius of the nearest fix to that point
        k = min(range(len(pts)), key=lambda j: haversine(pts[j], track_line[i][:2]))
        gale = max_gale_km(ps[k])
        flag = "INSIDE gale radius" if gale and d <= gale else "outside gale radius"
        print(f"    {country}: {d:6.0f} km from {island:14} (gale {gale:4.0f} km) {flag}")


def main():
    if len(sys.argv) != 3:
        sys.exit("Usage: python compare_tracks.py <working id> <failing id>")
    a, b = sys.argv[1], sys.argv[2]
    ta, tb = fetch(a), fetch(b)
    pa, pb = points(ta), points(tb)
    track_report(a, ta, pa)
    track_report(b, tb, pb)
    column_report(pa, pb, a, b)


if __name__ == "__main__":
    main()
