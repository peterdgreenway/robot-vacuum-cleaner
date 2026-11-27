# Robot Vacuum (Roborock) – FiestaBoard

**Version 2.0.0** connects FiestaBoard to the separate Roborock Service running on your NAS. The service owns Roborock authentication, device connections, polling, schedule enforcement and tracked-operation accounting. FiestaBoard does not connect directly to Roborock.

## Architecture

- **Roborock Service:** runs separately from FiestaBoard, normally at `http://192.168.100.99:8088`.
- **FiestaBoard plugin:** reads `/status` and synchronises the schedule through `/config`.
- **Refresh Now:** available on the service dashboard at the service URL. The data-plugin interface does not document a native settings-page action button; the plugin includes a callable `refresh_now()` helper but does not claim to render a FiestaBoard button.

## Configure

1. Deploy and test the Roborock Service first.
2. Install this repository through FiestaBoard's GitHub plugin installer.
3. Set **Roborock service URL** to `http://192.168.100.99:8088`.
4. Set the polling window and interval. Defaults are 07:15–21:00 and 60 seconds.
5. Save and confirm the plugin can read the service status.

The service should remain LAN-only. Do not forward port 8088 from your router or expose it to the public internet.

## Variables

`battery_level`, `battery`, `is_charging`, `is_docked`, `dock_state`, `robot_state`, `activity`, `cleaning_activity`, `current_room`, `room`, `cleaning_mode`, `cleaning_progress`, `cleaning_time_minutes`, `area_cleaned_m2`, `do_not_disturb`, `map_present`, `error`, `has_error`, `last_refresh`, `polling_start`, `polling_end`, `polling_interval_seconds`, `tracked_operations_today`, `daily_operation_limit`, `api_usage_percent`, `operations_remaining`, `next_refresh`.

Boolean values are presented as Yes/No/Unknown where possible. Missing room or status values remain Unknown rather than being guessed.

## Note layout

```text
{{robot_vacuum.line1}}
{{robot_vacuum.line2}}
{{robot_vacuum.line3}}
```

## Usage accounting qualification

The service reports **tracked operations** initiated by the service. It cannot count every internal HTTP/MQTT exchange performed inside python-roborock. The default limit of 1,000 is a configurable local safety ceiling, not a published Roborock quota.

See [docs/SETUP.md](docs/SETUP.md) for setup and troubleshooting.
