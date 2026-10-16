# Rapid Exposure Forecast (REF)

Runs the REF model on RiskScape for a cyclone track from the SPC API, waits for it to finish and downloads the outputs.

## Setup

Put your RiskScape API key in `.env`:

```bash
cp .env.example .env
```

Then edit the top of `REF.sh`:

- `TRACK_ID` - SPC cyclone track id
- `DOWNLOAD_OUTPUTS` - `true` / `false`

List track ids:

```bash
curl -s 'https://pacific-disaster-api.spc.int/partner_api/v1/cyclone_track/?format=json'
```

## Run

```bash
chmod +x REF.sh
./REF.sh
```

Outputs are saved to `outputs/<cyclone>_<issue time>/`.
