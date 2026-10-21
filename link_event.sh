#!/usr/bin/env bash

# Create a Partner API event (if it doesn't exist yet) and link a model run to it.
#   ./link_event.sh 14     # link Partner API model run 14

EVENT_TITLE="Tropical Cyclone Wati"
EVENT_DATETIME="2026-10-17T12:00:00Z"
EVENT_TYPE=1   # 1 = Tropical Cyclone
COUNTRY=4      # 1 VU, 2 TV, 3 TO, 4 CK, 5 WS
MODEL_RUN_ID="${1:?Usage: ./link_event.sh <partner api model run id>}"
API=https://opmthredds.gem.spc.int/partner_api/v1

PATH="/usr/bin:${PATH}"   # macOS curl (works with Zscaler)
cd "$(dirname "$0")"
source .env               # PARTNER_API_TOKEN

# find an event with this title and country
EVENT_ID=$(curl -s "${API}/event/?page_size=200&format=json" |
  jq -r --arg t "${EVENT_TITLE}" --argjson c "${COUNTRY}" \
    '[.results[] | select(.title == $t and .country == $c)][0].id // empty')

if [ -z "${EVENT_ID}" ]; then
  # create it with the run attached
  EVENT_ID=$(curl -s -H "Authorization: Token ${PARTNER_API_TOKEN}" \
    -H "Content-Type: application/json" -X POST "${API}/event/" \
    -d "$(jq -n --arg t "${EVENT_TITLE}" --arg d "${EVENT_DATETIME}" \
          --argjson e "${EVENT_TYPE}" --argjson c "${COUNTRY}" --argjson r "${MODEL_RUN_ID}" \
          '{title: $t, event_datetime: $d, event_type: $e, country: $c, model_run: $r}')" |
    jq -r '.id // empty')
  [ -n "${EVENT_ID}" ] || { echo "Could not create event '${EVENT_TITLE}'"; exit 1; }
  echo "Created event ${EVENT_ID}: ${EVENT_TITLE}"
else
  # link the run to the existing event
  curl -sf -H "Authorization: Token ${PARTNER_API_TOKEN}" \
    -H "Content-Type: application/json" -X PATCH "${API}/event/${EVENT_ID}/" \
    -d "{\"model_run\": ${MODEL_RUN_ID}}" > /dev/null ||
    { echo "Could not link run ${MODEL_RUN_ID} to event ${EVENT_ID}"; exit 1; }
  echo "Found event ${EVENT_ID}: ${EVENT_TITLE}"
fi

echo "Event ${EVENT_ID} now has model run: $(curl -s "${API}/event/${EVENT_ID}/?format=json" | jq -r .model_run)"
