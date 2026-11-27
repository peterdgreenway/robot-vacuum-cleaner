# Roborock Service – UGREEN NAS deployment

This is a separate container. It does not modify or restart FiestaBoard.

## NAS folders

Create these folders under the NAS Docker shared folder:

- `/volume1/docker/Roborock/data`
- `/volume1/docker/Roborock/credentials`

Place the existing authenticated `roborock_credentials.json` file in the credentials folder. Do not upload it to GitHub.

## Deploy

Use Docker > Project > Create and paste the contents of `docker-compose-ugreen.yml`. If your Docker shared folder is not mounted at `/volume1/docker`, edit only the two host paths in the volumes section to the actual path shown by File Manager.

The image is published by GitHub Actions to GHCR for linux/amd64. The first package publication may be private by default: in GitHub, open the published `roborock-service` package settings and change visibility to Public before pulling without registry credentials.

Open:

- Dashboard: http://192.168.100.99:8088/
- Health: http://192.168.100.99:8088/health
- Status: http://192.168.100.99:8088/status

Keep port 8088 on your trusted LAN. Do not configure router port forwarding.

## Accounting qualification

The service counts its own status-refresh operations. It cannot see every internal HTTP/MQTT exchange inside python-roborock. The default 1,000/day is a configurable local safety ceiling, not a published Roborock quota. Manual Refresh Now is also a tracked operation.
