#!/usr/bin/env bash

# API_KEY is read from .env (not committed), see .env.example
cd "$(dirname "$0")"
if [ ! -f .env ]; then
  echo "Missing .env - copy .env.example to .env and add your API key"
  exit 1
fi
source .env

PROJECT_SLUG=niwa/partner/rsmc-tcwc
MODEL_NAME=Rapid-Exposure-Forecast-GeoJSON


# check key is working
curl -u "TOKEN:${API_KEY}" https://riskscape.nz/api/ping


# upload to platform
#curl -s -u "TOKEN:${API_KEY}" \
#  -X PUT --data-binary @cyclone-latest.geojson \
#  "https://riskscape.nz/api/projects/by-full-slug/${PROJECT_SLUG}/files/by-path/Cyclone-Tracks/${CYCLONE_NAME}/${ISSUE_TIME}.geojson"


# Post it with managed: true
curl --location 'https://riskscape.nz/api/projects/by-full-slug/niwa/partner/rsmc-tcwc/runs/new' \
-u "TOKEN:${API_KEY}" \
--header 'Content-Type: application/json' \
--data '{
    "externalModelId" : "Rapid-Exposure-Forecast-GeoJSON",
    "managed": true,
    "parameters":{
        "hazard":{
            "label":"TC track",
            "value":"https://pacific-disaster-api.spc.int/partner_api/v1/cyclone_track/70/?format=json"
        }
    }
}' > model_run_response.txt



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