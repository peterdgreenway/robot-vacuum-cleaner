# Robot Vacuum (Roborock) Plugin for FiestaBoard

Live status, battery, fan speed, clean statistics and consumable levels from a Roborock vacuum using the official cloud API.

Designed for **Vestaboard Note** (15×3) but works on Flagship and Note arrays as well.

**Author:** peterdgreenway  
**Repository:** https://github.com/peterdgreenway/fiestaboard-plugin--robot-vacuum

---

## Features

- Real-time vacuum status (Cleaning / Docked / Returning / Paused …)
- Battery percentage + simple icon hint
- Fan speed
- Current clean time & area
- Consumable remaining life (main brush, side brush, filter, sensors)
- Compact `formatted` line that fits a Note in one glance
- Caching + configurable refresh interval

## Template Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `robot_vacuum.name` | Device name | `ROBOROCK S8` |
| `robot_vacuum.status` | Raw status string | `Cleaning` |
| `robot_vacuum.activity` | High-level activity | `CLEANING` |
| `robot_vacuum.battery` | Battery % | `87%` |
| `robot_vacuum.battery_icon` | FULL / HIGH / LOW / CRIT | `FULL` |
| `robot_vacuum.fan_speed` | Current fan mode | `max` |
| `robot_vacuum.clean_time` | Minutes of current job | `28m` |
| `robot_vacuum.clean_area` | Square metres cleaned | `42m2` |
| `robot_vacuum.error` | Error code or `OK` | `OK` |
| `robot_vacuum.docked` | `true` / `false` | `false` |
| `robot_vacuum.charging` | `true` / `false` | `false` |
| `robot_vacuum.cleaning` | `true` / `false` | `true` |
| `robot_vacuum.mop_attached` | `true` / `false` | `true` |
| `robot_vacuum.main_brush` | Remaining life % | `82%` |
| `robot_vacuum.side_brush` | Remaining life % | `91%` |
| `robot_vacuum.filter` | Remaining life % | `76%` |
| `robot_vacuum.sensor` | Remaining life % | `88%` |
| `robot_vacuum.formatted` | Compact Note line | `CLEANING  87%` |
| `robot_vacuum.last_updated` | Time of last fetch | `14:32` |

## Example Note Layout (15×3)

```
{{robot_vacuum.name}}
{{robot_vacuum.formatted}}
{{robot_vacuum.clean_area}} {{robot_vacuum.clean_time}}
```

## Example Flagship Layout

```
     ROBOT VACUUM
{{robot_vacuum.name}}
{{robot_vacuum.activity}}  {{robot_vacuum.battery}}
FAN {{robot_vacuum.fan_speed}}
{{robot_vacuum.clean_area}}  {{robot_vacuum.clean_time}}
BRUSH {{robot_vacuum.main_brush}}  FILT {{robot_vacuum.filter}}
```

## Requirements

- FiestaBoard ≥ 9.0.0
- `python-roborock` installed inside the FiestaBoard container / environment

```bash
pip install python-roborock
```

## Setup

See **[docs/SETUP.md](docs/SETUP.md)** for the one-time login flow that obtains the long-lived UserData token.

## License

MIT
