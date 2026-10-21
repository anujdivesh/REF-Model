#!/usr/bin/env bash
# push_outputs.sh - send finished RiskScape runs from outputs/ to the Partner API.
#
#   ./push_outputs.sh                          send every run folder in outputs/, oldest first
#   ./push_outputs.sh outputs/2026101906_Wati_20261019T060000Z     send just that one
#   ./push_outputs.sh --dry-run                show what would be sent, send nothing
#   ./push_outputs.sh --replace                load again a run the server already has
#
# Settings, in a .env file next to this script or in the environment:
#   PARTNER_API_TOKEN   the Partner API key (NOT the RiskScape key). Sent as a header.
#   COUNTRY             country code of the runs, default CK
#   OUTPUT_DIR          where the run folders are, default outputs
#   PARTNER_API_URL     default https://opmthredds.gem.spc.int/partner_api/v1
#
# Each run folder is named <cyclone name>_<issue time>, e.g. 2026101906_Wati_20261019T060000Z, and
# holds the files REF.sh downloaded (regional-summary.csv, wind-swaths.gpkg, ...).
#
# The server needs the SPC track the run was made from. This script finds it by the cyclone name in
# the folder name (the newest track with that name, so a re-uploaded track is picked up). If you
# want to be exact, put the track and run in <folder>/run.env and it is used instead:
#   TRACK_ID=214
#   MODEL_RUN_URL=https://riskscape.nz/api/model-runs/by-id/20529     (optional)
# REF.sh can write that file when it finishes:
#   printf 'TRACK_ID=%s\nMODEL_RUN_URL=%s\n' "${TRACK_ID}" "${MODEL_RUN_URL}" > "${RUN_DIR}/run.env"
#
# Needs: bash, curl, python3. Sending a run the server already has is harmless ("already on
# the server"), so it is safe to run this over the whole folder every time.

set -u

cd "$(dirname "$0")"
# .env fills in what the environment does not already set
if [ -f .env ]; then
  _saved_token="${PARTNER_API_TOKEN:-}"; _saved_country="${COUNTRY:-}"
  _saved_dir="${OUTPUT_DIR:-}"; _saved_url="${PARTNER_API_URL:-}"
  set -a; . ./.env; set +a
  [ -n "$_saved_token" ] && PARTNER_API_TOKEN="$_saved_token"
  [ -n "$_saved_country" ] && COUNTRY="$_saved_country"
  [ -n "$_saved_dir" ] && OUTPUT_DIR="$_saved_dir"
  [ -n "$_saved_url" ] && PARTNER_API_URL="$_saved_url"
fi

PARTNER_API_URL="${PARTNER_API_URL:-https://opmthredds.gem.spc.int/partner_api/v1}"
SPC_TRACKS_URL="${SPC_TRACKS_URL:-https://pacific-disaster-api.spc.int/partner_api/v1/cyclone_track/}"
COUNTRY="${COUNTRY:-CK}"
OUTPUT_DIR="${OUTPUT_DIR:-outputs}"
REQUIRED="regional-impacts.geojson regional-summary.csv total-exposed-by-country.csv total-by-windspeed.csv total-by-track-distance.csv exposure-by-cluster.geojson"

DRY_RUN=0
REPLACE=0
FOLDERS=""
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --replace) REPLACE=1 ;;
    -h|--help) sed -n '2,28p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) echo "Unknown option: $arg (see --help)"; exit 2 ;;
    *) FOLDERS="$FOLDERS
${arg%/}" ;;
  esac
done

if [ -z "${PARTNER_API_TOKEN:-}" ]; then
  echo "PARTNER_API_TOKEN is not set. Put it in .env next to this script:"
  echo "  PARTNER_API_TOKEN=<the Partner API key>"
  exit 2
fi
for tool in curl python3; do
  command -v "$tool" >/dev/null 2>&1 || { echo "$tool is not installed"; exit 2; }
done

if [ -z "$FOLDERS" ]; then
  [ -d "$OUTPUT_DIR" ] || { echo "No $OUTPUT_DIR folder here"; exit 2; }
  FOLDERS="$(find "$OUTPUT_DIR" -mindepth 1 -maxdepth 1 -type d | sort)"
fi
[ -n "$FOLDERS" ] || { echo "No run folders found in $OUTPUT_DIR"; exit 2; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# The SPC's recent tracks as "id<TAB>name" lines, read from the SPC server.
load_tracks() {
  if curl -s -m 180 "${SPC_TRACKS_URL}?format=json" -o "$WORK/tracks.json" \
     && python3 - "$WORK/tracks.json" > "$WORK/tracks.tsv" 2>/dev/null <<'PY'
import json, sys
rows = json.load(open(sys.argv[1]))
rows = rows.get("results", rows) if isinstance(rows, dict) else rows
for r in rows:
    print(f"{r['id']}\t{r['cyclone_name']}")
PY
  then return 0; fi
  : > "$WORK/tracks.tsv"
  echo "  (could not read the SPC track list; folders need a run.env with TRACK_ID)"
}

# the id of the newest track with this name, or nothing
track_id_for() {
  awk -F'\t' -v name="$1" '$2 == name && $1 + 0 > best { best = $1 + 0 } END { if (best) print best }' "$WORK/tracks.tsv"
}

# prints "<label> <detail>" for a server reply; $1 = http code, $2 = body file
explain() {
  python3 - "$1" "$2" <<'PY'
import json, sys
code, path = sys.argv[1], sys.argv[2]
try:
    body = json.load(open(path))
except Exception:
    body = {}
detail = body.get("detail") if isinstance(body, dict) else None
if code == "201":
    print(f"loaded: {body.get('advisory')}, run {body.get('run')}, {body.get('outputs')} outputs, "
          + ("now the advisory the dashboard shows" if body.get("shown") else "kept beside a newer one"))
elif code == "200" and isinstance(body, dict) and body.get("already_imported"):
    print(f"already on the server ({body.get('advisory')}, run {body.get('run')}), nothing changed")
elif code == "400":
    print(f"refused: {detail or body}")
elif code in ("401", "403"):
    print(f"not allowed ({detail or 'no reason given'}). Check PARTNER_API_TOKEN: it is the Partner API key, "
          "sent as a header, not the RiskScape key.")
else:
    print(f"unexpected reply {detail or body}")
PY
}

load_tracks   # once, here: inside the loop it would run in a subshell and fetch again for every folder
: > "$WORK/results"
echo "$FOLDERS" | while IFS= read -r dir; do
  [ -n "$dir" ] || continue
  base="$(basename "$dir")"
  echo
  echo "== $base"
  if [ ! -d "$dir" ]; then echo "  not a folder, skipped"; echo SKIP >> "$WORK/results"; continue; fi

  missing=""
  for f in $REQUIRED; do [ -f "$dir/$f" ] || missing="$missing $f"; done
  if [ -n "$missing" ]; then
    echo "  skipped: the folder is missing$missing (the run may not have finished downloading)"
    echo SKIP >> "$WORK/results"; continue
  fi

  TRACK_ID=""; MODEL_RUN_URL=""
  [ -f "$dir/run.env" ] && . "$dir/run.env"
  name="$(echo "$base" | sed -E 's/_[0-9]{8}T[0-9]{6}Z$//')"
  if [ -z "$TRACK_ID" ]; then TRACK_ID="$(track_id_for "$name")"; fi
  if [ -z "$TRACK_ID" ]; then
    echo "  skipped: no track named $name among the SPC's recent tracks."
    echo "  Put TRACK_ID=<id> in $dir/run.env (the id is in the run's hazard input) and run it again."
    echo SKIP >> "$WORK/results"; continue
  fi
  TRACK_URL="${SPC_TRACKS_URL}${TRACK_ID}/?format=json"
  echo "  track $TRACK_ID ($name)${MODEL_RUN_URL:+, run $MODEL_RUN_URL}"

  rm -f "$WORK/run.zip"
  (cd "$(dirname "$dir")" && python3 -m zipfile -c "$WORK/run.zip" "$base") || { echo "  could not zip the folder"; echo FAIL >> "$WORK/results"; continue; }
  echo "  zip: $(wc -c < "$WORK/run.zip" | tr -d ' ') bytes"
  if [ "$DRY_RUN" = 1 ]; then echo "  dry run: not sent"; echo SKIP >> "$WORK/results"; continue; fi

  extra=""
  [ -n "$MODEL_RUN_URL" ] && extra="$extra -F riskscape_run=$MODEL_RUN_URL"
  [ "$REPLACE" = 1 ] && extra="$extra -F replace=true"
  # shellcheck disable=SC2086
  code="$(curl -s -m 300 -o "$WORK/reply.json" -w '%{http_code}' \
    -H "Authorization: Token ${PARTNER_API_TOKEN}" \
    -F country="$COUNTRY" -F track_url="$TRACK_URL" -F outputs=@"$WORK/run.zip" $extra \
    "${PARTNER_API_URL}/model_run/import/")" || code="000"
  if [ "$code" = "000" ]; then
    echo "  could not reach ${PARTNER_API_URL} (network or timeout)"; echo FAIL >> "$WORK/results"; continue
  fi
  echo "  HTTP $code - $(explain "$code" "$WORK/reply.json")"
  case "$code" in
    201) echo SENT >> "$WORK/results" ;;
    200) echo ALREADY >> "$WORK/results" ;;
    *)   echo FAIL >> "$WORK/results" ;;
  esac
done

echo
sent=$(grep -c '^SENT' "$WORK/results" 2>/dev/null); already=$(grep -c '^ALREADY' "$WORK/results" 2>/dev/null)
failed=$(grep -c '^FAIL' "$WORK/results" 2>/dev/null); skipped=$(grep -c '^SKIP' "$WORK/results" 2>/dev/null)
echo "Done: ${sent:-0} loaded, ${already:-0} already there, ${skipped:-0} skipped, ${failed:-0} failed."
[ "${failed:-0}" = 0 ]
 