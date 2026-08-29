"""Tests for localization/zones.py: simulation-focused named-zone lookup
over the project's existing Webots world-frame Position, not real GPS."""
import math

import pytest

from localization.zones import (
    DEFAULT_ZONE_RADIUS_M,
    PATROL_ZONES,
    PatrolZone,
    describe_position,
    localize,
    nearest_zone,
)
from shared.models import Position


def test_zone_definitions_match_drone_patrol_route():
    """config/Green_Guardians_settings.yaml's drone.patrol_route.waypoints
    (what PATROL_ZONES is built from) must not drift from
    drone/mission.py's PATROL_ROUTE (what the drone actually flies) -
    both are meant to describe the same six waypoints."""
    from drone.mission import PATROL_ROUTE

    expected = {wp["name"]: wp["position"] for wp in PATROL_ROUTE}
    actual = {z.name: (z.center.x, z.center.y, z.center.z) for z in PATROL_ZONES}
    assert actual == expected


def test_nearest_zone_at_exact_waypoint_is_zero_distance():
    fire_observation = next(z for z in PATROL_ZONES if z.name == "fire_observation")
    zone, distance = nearest_zone(fire_observation.center)
    assert zone.name == "fire_observation"
    assert distance == pytest.approx(0.0)


def test_nearest_zone_ignores_altitude():
    fire_observation = next(z for z in PATROL_ZONES if z.name == "fire_observation")
    high_above = Position(fire_observation.center.x, fire_observation.center.y, 200.0)
    zone, distance = nearest_zone(high_above)
    assert zone.name == "fire_observation"
    assert distance == pytest.approx(0.0)


def test_localize_within_radius_returns_zone_name():
    fire_observation = next(z for z in PATROL_ZONES if z.name == "fire_observation")
    nearby = Position(fire_observation.center.x + 1.0, fire_observation.center.y, fire_observation.center.z)
    assert localize(nearby) == "fire_observation"


def test_localize_outside_every_zone_returns_none():
    far_away = Position(500.0, 500.0, 12.0)
    assert localize(far_away) is None


def test_describe_position_within_zone():
    fire_observation = next(z for z in PATROL_ZONES if z.name == "fire_observation")
    assert describe_position(fire_observation.center) == "within fire_observation"


def test_describe_position_outside_every_zone_reports_distance():
    custom_zone = PatrolZone(name="test_zone", center=Position(0.0, 0.0, 12.0), radius_m=1.0)
    far_position = Position(10.0, 0.0, 12.0)
    description = describe_position(far_position, zones=[custom_zone])
    assert description == "10.0m from test_zone (nearest zone)"


def test_nearest_zone_with_no_zones_configured():
    zone, distance = nearest_zone(Position(0.0, 0.0, 0.0), zones=[])
    assert zone is None
    assert math.isinf(distance)


def test_describe_position_with_no_zones_configured():
    assert describe_position(Position(0.0, 0.0, 0.0), zones=[]) == "no patrol zones configured"


def test_default_zone_radius_keeps_all_named_zones_from_overlapping():
    """Sanity check for the chosen DEFAULT_ZONE_RADIUS_M: no two named
    zones should be closer together than 2x the radius, or localize()
    could attribute a position to the wrong zone's territory."""
    for i, a in enumerate(PATROL_ZONES):
        for b in PATROL_ZONES[i + 1:]:
            distance = math.hypot(a.center.x - b.center.x, a.center.y - b.center.y)
            assert distance > 2 * DEFAULT_ZONE_RADIUS_M, (
                f"{a.name} and {b.name} are only {distance:.2f}m apart, "
                f"closer than 2x DEFAULT_ZONE_RADIUS_M ({2 * DEFAULT_ZONE_RADIUS_M}m)"
            )
