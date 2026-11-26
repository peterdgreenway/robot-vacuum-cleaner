# Robot Vacuum (Roborock) – FiestaBoard

Version **1.5.0** adds normalised, human-readable status fields intended for use in FiestaBoard templates. It has been developed against the Roborock Saros 20 and the `python-roborock` V1 API.

## Example Vestaboard Note

```text
SAROS 20 - 34%
VACUUMING
KITCHEN
```

Use the `line1`, `line2` and `line3` variables for the ready-made 3 × 15 character lines, or compose your own display from the individual fields.

## Fields

| Variable | Example | Meaning |
|---|---|---|
| `name` | `Roborock Saros 20` | Device name |
| `battery_level` | `34` | Battery percentage as a number |
| `battery` | `34%` | Battery with percent sign |
| `is_charging` | `Yes` / `No` / `Unknown` | Actual charging state; delayed charging is not treated as charging |
| `is_docked` | `Yes` / `No` / `Unknown` | Whether docked, independently of charging |
| `dock_state` | `Charging`, `Delayed Charge`, `Fully Charged` | Human-readable dock state |
| `robot_state` | `cleaning`, `charging`, `returning` | Normalised robot state |
| `activity` | `Cleaning`, `Charging` | General robot activity/state |
| `cleaning_activity` | `Vacuuming`, `Mopping`, `Vac & Mop`, `Cruise` | Cleaning action inferred from the selected cleaning mode |
| `current_room` | `Kitchen` | Resolved current room name, or `Unknown` |
| `room` | `Kitchen` | Alias for `current_room` |
| `cleaning_mode` | `Vac then Mop`, `Vac And Mop`, `Mop`, `Vacuum`, `Cruise` | Human-readable selected mode when exposed by the API |
| `cleaning_progress` | `65` | Cleaning progress percentage |
| `cleaning_time_minutes` | `18.0` | Elapsed cleaning time in minutes |
| `area_cleaned_m2` | `24.5` | Area cleaned in square metres |
| `do_not_disturb` | `Yes` / `No` / `Unknown` | DND enabled state |
| `map_present` | `Yes` / `No` / `Unknown` | Map-present flag |
| `error` | `None` | Error description |
| `has_error` | `Yes` / `No` | Whether an error is reported |

Boolean values are exposed as **Yes**, **No** or **Unknown**. Missing data is never silently converted to No.

## Dock and mode labels

The plugin uses these exact display labels where the Roborock API supplies a recognised value:

- Dock: `Charging`, `Delayed Charge`, `Fully Charged`
- Cleaning mode: `Vac then Mop`, `Vac And Mop`, `Mop`, `Vacuum`, `Cruise`

A docked robot waiting for its configured off-peak charging window is reported as `Delayed Charge` and `is_charging: No`.

## Room, routines and zones

Room names are resolved from available current-segment and map/room information when the installed library and firmware expose it. If the current room cannot be matched confidently, the field is `Unknown` rather than a guessed room. Routines and user-defined multi-room zones are not yet executed or separately represented in this release; they are a subsequent development item.

## Connection lifecycle

Each refresh creates, uses and closes its Roborock device manager within one asyncio event loop. This avoids reusing MQTT tasks and connections across the separate event loops created by repeated synchronous FiestaBoard refresh calls.

## Setup

See `docs/SETUP.md` for the credential setup process. Keep the UserData JSON private and never include it in diagnostic logs or screenshots.
