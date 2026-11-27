# Setup – FiestaBoard Roborock Service plugin

## Prerequisite

Deploy the separate Roborock Service container on the NAS first. Confirm these endpoints:

- `http://192.168.100.99:8088/health` – health check
- `http://192.168.100.99:8088/status` – current robot status
- `http://192.168.100.99:8088/` – service dashboard and Refresh Now control

Do not put Roborock credentials or UserData JSON into FiestaBoard. Credentials belong in the service container's protected credentials directory.

## Install

Use the FiestaBoard GitHub plugin installer with:

`https://github.com/peterdgreenway/robot-vacuum-cleaner`

Configure the plugin's service URL as `http://192.168.100.99:8088`.

## Settings

- Night patrol: 03:00–04:00, every 15 minutes
- Peak cleaning: 07:30–10:30, every 10 minutes
- All other times: every 60 minutes
- Daily tracked-operation safety limit: 1,000

Refreshes are aligned to each window's start (for example, 03:00, 03:15 and 03:30). The service enforces the schedule and usage ceiling.

## Refresh Now

Open the service dashboard at `http://192.168.100.99:8088/` and use its Refresh Now control. FiestaBoard's documented data-plugin interface does not expose a native settings-page action button.

## Security

Keep the service on your trusted LAN. Do not configure router port forwarding for port 8088. Do not share credentials, token files or screenshots containing them.
