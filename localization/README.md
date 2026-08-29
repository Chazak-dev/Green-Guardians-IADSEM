# localization/

A simple, simulation-focused localization system: labels a position with
the nearest **named patrol zone**, instead of computing an exact real-world
location. Real GPS/3-D geolocation of hazards is explicitly out of scope
for this project (see `config/Green_Guardians_settings.yaml`'s
`investigation.out_of_scope`) - this module doesn't attempt it either.

## What it does

`zones.py` defines a `PatrolZone` (a name + a center `Position` + a radius
in metres) for each of the six named waypoints in
`drone.patrol_route.waypoints` (`config/Green_Guardians_settings.yaml`) -
the same waypoints `drone/mission.py`'s `PATROL_ROUTE` flies. Given any
`Position` (the same Webots world-frame `x, y, z` metres, z positive-up,
that `DetectionInput` / `DroneStatus` / `AlertOutput` already use
everywhere else - **not** a separate coordinate system), it can:

- `localize(position)` - the zone name `position` falls inside, or `None`
  if it's outside every known zone's radius.
- `nearest_zone(position)` - the closest zone and the horizontal distance
  to it, regardless of radius.
- `describe_position(position)` - a human-readable string, e.g.
  `"within forest_edge"` or `"6.3m from patrol_west (nearest zone)"`.

Distance is horizontal only (x, y), ignoring altitude - the same reasoning
`backend/alert_manager.py`'s suppression-radius check uses: ground location
identifies "the same place," not the altitude a reading happened to be
taken at.

This module has **no dependency on `drone/`** (`drone/drone_controller.py`
requires a real Webots install just to import), so it can be used from
anywhere - a test, a script, a future dashboard feature - without needing
Webots running.

## Example

```python
from localization import localize, describe_position
from shared.models import Position

p = Position(-4.2, -1.6, 12.0)
localize(p)            # "fire_observation"
describe_position(p)   # "within fire_observation"
```

## Running the tests

```
pytest tests/test_localization.py -v
```

Covers: zone lookup at/near/far from a waypoint, altitude being ignored,
the empty-zones edge case, and a consistency check that
`drone.patrol_route.waypoints` (what this module reads) and
`drone/mission.py`'s `PATROL_ROUTE` (what the drone actually flies) haven't
drifted apart from each other.
