"""Simple simulation-focused localization: labels a Webots world-frame
Position with the nearest named patrol zone.

Deliberately NOT real GPS/3-D geolocation of hazards - this only answers
"which named patrol area is this position near," the same coarse-grained
spirit as config's investigation.out_of_scope ("Nobody should try to
calculate [a hazard's] exact position"). Coordinates are the project's
existing Webots world-frame Position (x, y, z metres, z positive up) - the
same one DetectionInput/DroneStatus/AlertOutput already use everywhere
else, not a separate/parallel coordinate system.

Deliberately NOT dependent on drone/ (drone/drone_controller.py requires a
real Webots install just to import, since it does `from controller import
Robot` at module level). Zones are read straight from
config/Green_Guardians_settings.yaml's drone.patrol_route.waypoints - the
same waypoints drone/mission.py's PATROL_ROUTE flies, kept in sync because
both are written from that one config
(tests/test_localization.py cross-checks the two haven't drifted apart).
"""
import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import yaml

from config.paths import CONFIG_PATH
from shared.models import Position

# Under half the tightest real gap between any two named waypoints (~2.06m,
# forest_edge to exit_forest - see drone/mission.py's PATROL_ROUTE) so
# adjacent zones don't overlap by default. Still comfortably above
# DroneController.TARGET_PRECISION_M (0.5m), so it's larger than pure
# positioning noise.
DEFAULT_ZONE_RADIUS_M = 1.0


@dataclass(frozen=True)
class PatrolZone:
    name: str
    center: Position
    radius_m: float = field(default=DEFAULT_ZONE_RADIUS_M)


def _horizontal_distance(a: Position, b: Position) -> float:
    """Ground distance only, ignoring altitude - same reasoning as
    backend/alert_manager.py's suppression-radius check: horizontal location
    identifies "the same place," not the drone's altitude when it measured it."""
    return math.hypot(a.x - b.x, a.y - b.y)


def load_patrol_zones(config_path=CONFIG_PATH) -> List[PatrolZone]:
    """Build named zones from drone.patrol_route.waypoints in
    config/Green_Guardians_settings.yaml."""
    with open(config_path, "r", encoding="utf-8") as f:
        settings = yaml.safe_load(f)
    waypoints = settings["drone"]["patrol_route"]["waypoints"]
    return [
        PatrolZone(name=wp["name"], center=Position(wp["x"], wp["y"], wp["z"]))
        for wp in waypoints
    ]


PATROL_ZONES: List[PatrolZone] = load_patrol_zones()


def nearest_zone(
    position: Position, zones: Optional[List[PatrolZone]] = None
) -> Tuple[Optional[PatrolZone], float]:
    """Return (closest PatrolZone, horizontal distance to it in metres).
    (None, inf) if no zones are configured."""
    zones = PATROL_ZONES if zones is None else zones
    if not zones:
        return None, float("inf")
    closest = min(zones, key=lambda z: _horizontal_distance(position, z.center))
    return closest, _horizontal_distance(position, closest.center)


def localize(position: Position, zones: Optional[List[PatrolZone]] = None) -> Optional[str]:
    """Name of the zone `position` falls inside (within that zone's
    radius_m), or None if it's outside every known zone."""
    zone, distance = nearest_zone(position, zones)
    if zone is not None and distance <= zone.radius_m:
        return zone.name
    return None


def describe_position(position: Position, zones: Optional[List[PatrolZone]] = None) -> str:
    """Human-readable localization string for logs/dashboard, e.g.
    'within forest_edge' or '6.3m from patrol_west (nearest zone)'."""
    zone, distance = nearest_zone(position, zones)
    if zone is None:
        return "no patrol zones configured"
    if distance <= zone.radius_m:
        return f"within {zone.name}"
    return f"{distance:.1f}m from {zone.name} (nearest zone)"
