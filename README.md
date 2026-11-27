# Robot Vacuum (Roborock) – FiestaBoard

**Version 2.2.0** connects FiestaBoard to the separate Roborock Service running on your NAS. The service owns Roborock authentication, device connections, polling, schedule enforcement and tracked-operation accounting. FiestaBoard does not connect directly to Roborock.

## Architecture

- **Roborock Service:** runs separately from FiestaBoard, normally at `http://192.168.100.99:8088`.
- **FiestaBoard plugin:** reads `/status` and synchronises the schedule through `/config`.
- **Refresh Now:** available on the service dashboard at the service URL. The data-plugin interface does not document a native settings-page action button; the plugin includes a callable `refresh_now()` helper but does not claim to render a FiestaBoard button.

## Configure

1. Deploy and test the Roborock Service first.
2. Install this repository through FiestaBoard's GitHub plugin installer.
3. Set **Roborock service URL** to `http://192.168.100.99:8088`.
4. Set the time-of-day refresh schedule. Defaults are 03:00–04:00 every 15 minutes, 07:30–10:30 every 10 minutes and every 60 minutes at all other times.
5. Save and confirm the plugin can read the service status.

The service should remain LAN-only. Do not forward port 8088 from your router or expose it to the public internet.

## Variables

`last_run_date`, `last_run_time`, `last_run_datetime`, `last_refresh_date`, `last_refresh_time`, `last_refresh_datetime`, `total_cleaning_time`, `total_cleaning_time_seconds`, `total_cleaning_time_minutes`, `total_cleaned_area_m2`, `total_cleaning_count`, `battery_level`, `battery`, `is_charging`, `is_docked`, `dock_state`, `robot_state`, `activity`, `cleaning_activity`, `current_room`, `room`, `cleaning_mode`, `cleaning_progress`, `cleaning_time_minutes`, `area_cleaned_m2`, `do_not_disturb`, `map_present`, `error`, `has_error`, `last_refresh`, `night_start`, `night_end`, `night_interval_seconds`, `peak_start`, `peak_end`, `peak_interval_seconds`, `default_interval_seconds`, `tracked_operations_today`, `daily_operation_limit`, `api_usage_percent`, `operations_remaining`, `next_refresh`.

Date variables use `DD-MMM-YY` (for example `27-NOV-26`), time variables use 24-hour `HH:MM` and combined variables use `DD-MMM-YY HH:MM`. All timestamps are converted to Europe/London local time. `total_cleaning_time` is shown as hours and minutes (for example `4h 5m`) and `total_cleaned_area_m2` is the lifetime cleaned area in square metres.

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
