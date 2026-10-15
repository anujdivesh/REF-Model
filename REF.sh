#!/usr/bin/env bash

API_KEY=12uORNOW7Lk8AqphTEWMsA==
PROJECT_SLUG=niwa/partner/rsmc-tcwc
MODEL_NAME=Rapid-Exposure-Forecast-GeoJSON
TRACK_ID=74
TRACK_URL="https://pacific-disaster-api.spc.int/partner_api/v1/cyclone_track/${TRACK_ID}/?format=json"
DOWNLOAD_OUTPUTS=true   # download the run's outputs when it finishes (true/false)
OUTPUT_DIR=outputs      # outputs go in ${OUTPUT_DIR}/<cyclone name>_<issue time>/


# check key is working
curl -u "TOKEN:${API_KEY}" https://riskscape.nz/api/ping

# download the track from spc server
curl -s "${TRACK_URL}" > cyclone-latest.geojson

# extract from cyclone-latest.geojson
#CYCLONE_NAME=$(jq -r .cyclone_name cyclone-latest.geojson)
#ISSUE_TIME=$(jq -r .issued_time cyclone-latest.geojson)
CYCLONE_NAME=$(sed -n 's/.*"cyclone_name":"\([^"]*\)".*/\1/p' cyclone-latest.geojson)
ISSUE_TIME=$(sed -n 's/.*"issued_time":"\([^"]*\)".*/\1/p' cyclone-latest.geojson)

RUN_NAME="${CYCLONE_NAME} issued ${ISSUE_TIME}"

echo "Cyclone: ${CYCLONE_NAME}, issued: ${ISSUE_TIME}"


# upload to platform
#curl -s -u "TOKEN:${API_KEY}" \
#  -X PUT --data-binary @cyclone-latest.geojson \
#  "https://riskscape.nz/api/projects/by-full-slug/${PROJECT_SLUG}/files/by-path/Cyclone-Tracks/${CYCLONE_NAME}/${ISSUE_TIME}.geojson"


# Post it with managed: true
curl -s -u "TOKEN:${API_KEY}" \
  -X POST -H "Content-Type: application/json" \
  "https://riskscape.nz/api/projects/by-full-slug/${PROJECT_SLUG}/runs/new" \
  -d "{
    \"externalModelId\": \"${MODEL_NAME}\",
    \"managed\": true,
    \"parameters\": {
        \"hazard\": {
            \"label\": \"TC track\",
            \"value\": \"${TRACK_URL}\"
        }
    }
}" > model_run_response.txt



# get the run id from the response, stop if the run wasn't created
MODEL_RUN_ID=$(jq -r '.id // empty' model_run_response.txt)
if [ -z "${MODEL_RUN_ID}" ]; then
  echo "Model run not created, response was:"
  cat model_run_response.txt
  exit 1
fi
MODEL_RUN_URL="https://riskscape.nz/api/model-runs/by-id/${MODEL_RUN_ID}"
echo "[run] ${MODEL_RUN_ID} created"

# poll the run until it finishes, fails or times out
POLL_INTERVAL=5      # seconds between checks
POLL_TIMEOUT=1800    # give up after this many seconds
START=$(date +%s)

# print how long the run took, from the platform's timestamps (ms)
print_run_time() {
  echo "$1" | jq -r '
    def fmt: (. / 1000 | floor) as $s
      | "\($s / 3600 | floor)h \($s % 3600 / 60 | floor)m \($s % 60)s";
    "[run] model run time: \((.finishedAt - .startedAt) | fmt)",
    "[run] total time (incl. queue): \((.finishedAt - .createdAt) | fmt)"'
}

while true; do
  if ! RUN=$(curl -sf -u "TOKEN:${API_KEY}" "${MODEL_RUN_URL}"); then
    echo "[run] ${MODEL_RUN_ID} status request failed"
    exit 1
  fi
  STATE=$(echo "${RUN}" | jq -r '.state')
  FINISHED=$(echo "${RUN}" | jq -r '.finished')
  FAILURE=$(echo "${RUN}" | jq -c '.failureDetail')

  if [ "${FINISHED}" = "true" ]; then
    # a finished run is an error if it has a failureDetail or a FAILED state
    if [ "${FAILURE}" != "null" ] || [ "${STATE}" = "FAILED" ]; then
      echo "[run] ${MODEL_RUN_ID} FAILED (state: ${STATE})"
      echo "${RUN}" | jq '.failureDetail'
      print_run_time "${RUN}"
      exit 1
    fi
    echo "[run] ${MODEL_RUN_ID} done: ${STATE}"
    print_run_time "${RUN}"
    break
  fi

  if [ $(( $(date +%s) - START )) -gt ${POLL_TIMEOUT} ]; then
    echo "[run] ${MODEL_RUN_ID} timed out, still ${STATE}"
    exit 1
  fi

  echo "[run] ${MODEL_RUN_ID} ${STATE}... waiting ${POLL_INTERVAL}s"
  sleep ${POLL_INTERVAL}
done


# it ran fine, give it a name so it does not get deleted
# (not fatal: carry on to the downloads if naming fails)
NAME_RESPONSE=$(curl -s -w '\n%{http_code}' -u "TOKEN:${API_KEY}" \
  -X PATCH -H "Content-Type: application/json" \
  "${MODEL_RUN_URL}" \
  -d "$(jq -n --arg name "${RUN_NAME}" '{name: $name}')")
NAME_STATUS=$(echo "${NAME_RESPONSE}" | tail -n 1)
if [ "${NAME_STATUS}" -ge 200 ] && [ "${NAME_STATUS}" -lt 300 ]; then
  echo "[run] ${MODEL_RUN_ID} named: $(curl -s -u "TOKEN:${API_KEY}" "${MODEL_RUN_URL}" | jq -r .name)"
else
  echo "[run] ${MODEL_RUN_ID} could not be named (HTTP ${NAME_STATUS}), continuing:"
  echo "${NAME_RESPONSE}" | sed '$d'
fi


# download all outputs into a folder named by cyclone and issue time
if [ "${DOWNLOAD_OUTPUTS}" = "true" ]; then
  # 2026-10-14T23:13:41Z -> 20261014T231341Z (no ':' in folder names)
  RUN_DIR="${OUTPUT_DIR}/${CYCLONE_NAME}_${ISSUE_TIME//[-:]/}"
  mkdir -p "${RUN_DIR}"

  echo "${RUN}" | jq -r '.outputs[] | select(.state == "COMPLETE") | [.name, .mediaType] | @tsv' |
  while IFS=$'\t' read -r OUT_NAME MEDIA_TYPE; do
    case "${MEDIA_TYPE}" in
      text/csv)                        EXT=csv ;;
      application/geo+json)            EXT=geojson ;;
      application/geopackage+sqlite3)  EXT=gpkg ;;
      application/json)                EXT=json ;;
      *)                               EXT=${MEDIA_TYPE##*/} ;;
    esac
    if curl -sf -u "TOKEN:${API_KEY}" \
      "${MODEL_RUN_URL}/output/${OUT_NAME}/download" \
      -o "${RUN_DIR}/${OUT_NAME}.${EXT}"; then
      echo "[run] downloaded ${RUN_DIR}/${OUT_NAME}.${EXT}"
    else
      echo "[run] FAILED to download ${OUT_NAME}"
    fi
  done
fi
