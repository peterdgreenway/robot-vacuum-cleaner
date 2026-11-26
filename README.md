# Robot Vacuum (Roborock) – Vestaboard Note

**Strict 3 × 15 character layout.**

Live status from a Roborock vacuum (tested with **Saros 20**).  
When the robot is cleaning and the current room can be resolved, the third line shows the room name.

**Author:** peterdgreenway  
**Repo:** https://github.com/peterdgreenway/fiestaboard-plugin--robot-vacuum

---

## Recommended page (exactly 3 lines)

```
{{robot_vacuum.line1}}
{{robot_vacuum.line2}}
{{robot_vacuum.line3}}
```

### Example output (Saros 20)

```
SAROS 20
CLEAN  87%
KITCHEN
```

```
SAROS 20
CHARGE 100%
READY
```

```
SAROS 20
PAUSE  42%
LIVING ROOM
```

- While cleaning → `line3` prefers the **room name** (if available).
- Otherwise → area + time, or `READY`.

---

## Variables (all ≤ 15 characters)

| Variable | Max | Description | Example |
|----------|-----|-------------|---------|
| `line1` | 15 | Device name | `SAROS 20` |
| `line2` | 15 | Activity + battery | `CLEAN  87%` |
| `line3` | 15 | Room **or** area/time | `KITCHEN` |
| `name` | 15 | Device name | `SAROS 20` |
| `activity` | 15 | Short status | `CLEAN` |
| `battery` | 4 | Battery | `87%` |
| `status` | 15 | Same as activity | `CLEAN` |
| `room` | 15 | Current room (or —) | `KITCHEN` |
| `area_time` | 15 | Area + minutes | `42M2 28M` |
| `error` | 15 | OK or error code | `OK` |

---

## Room support

The plugin tries to resolve the current room via the map/segment data that the Saros 20 (and other map-capable models) expose.  

If the room cannot be determined (robot docked, map not yet loaded, older firmware, etc.) it falls back cleanly to area/time or `READY`. Room names are truncated to 15 characters.

---

## Requirements

```bash
pip install python-roborock
```

See **docs/SETUP.md** for the one-time UserData token.

## License

MIT
