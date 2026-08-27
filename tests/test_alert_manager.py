from backend.alert_manager import AlertManager
from shared.constants import POST_ALERT_SUPPRESSION_RADIUS_M
from shared.models import InvestigationResult, Position


def _investigation(**overrides) -> InvestigationResult:
    fields = dict(
        investigation_id="inv-1",
        detection_id="det-1",
        started_at="2026-08-15T10:00:00Z",
        completed_at="2026-08-15T10:00:05Z",
        hazard="fire",
        result="CONFIRMED",
        observations_checked=5,
        positive_observations=3,
        representative_confidence=0.9,
        evidence_image_path=None,
    )
    fields.update(overrides)
    return InvestigationResult(**fields)


def test_create_alert_builds_confirmed_output_and_records_history():
    manager = AlertManager()
    position = Position(1.0, 2.0, 12.0)

    alert = manager.create_alert(_investigation(), position)

    assert alert.status == "CONFIRMED"
    assert alert.investigation_id == "inv-1"
    assert alert.detection_id == "det-1"
    assert alert.hazard == "fire"
    assert alert.confidence == 0.9
    assert alert.observed_position == position
    assert manager.alert_history == [alert]


def test_create_alert_defaults_confidence_when_representative_missing():
    manager = AlertManager()
    alert = manager.create_alert(_investigation(representative_confidence=None), Position(0, 0, 0))
    assert alert.confidence == 0.0


def test_is_suppressed_false_with_no_history():
    manager = AlertManager()
    assert manager.is_suppressed(Position(0, 0, 0)) is False


def test_is_suppressed_true_within_radius():
    manager = AlertManager()
    manager.create_alert(_investigation(), Position(0.0, 0.0, 12.0))
    nearby = Position(POST_ALERT_SUPPRESSION_RADIUS_M - 0.1, 0.0, 12.0)
    assert manager.is_suppressed(nearby) is True


def test_is_suppressed_false_outside_radius():
    manager = AlertManager()
    manager.create_alert(_investigation(), Position(0.0, 0.0, 12.0))
    far = Position(POST_ALERT_SUPPRESSION_RADIUS_M + 0.1, 0.0, 12.0)
    assert manager.is_suppressed(far) is False


def test_is_suppressed_ignores_altitude():
    manager = AlertManager()
    manager.create_alert(_investigation(), Position(0.0, 0.0, 12.0))
    same_xy_different_altitude = Position(0.0, 0.0, 200.0)
    assert manager.is_suppressed(same_xy_different_altitude) is True


def test_is_suppressed_checks_against_most_recent_alert():
    manager = AlertManager()
    manager.create_alert(_investigation(), Position(0.0, 0.0, 12.0))
    manager.create_alert(_investigation(investigation_id="inv-2"), Position(100.0, 100.0, 12.0))
    assert manager.is_suppressed(Position(0.0, 0.0, 12.0)) is False
    assert manager.is_suppressed(Position(100.0, 100.0, 12.0)) is True
