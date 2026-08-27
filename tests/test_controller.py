from datetime import datetime, timedelta, timezone

import pytest

from backend.controller import MissionController
from shared.constants import (
    CAMERA_HEIGHT,
    CAMERA_WIDTH,
    CANDIDATE_TRIGGER_THRESHOLD,
    CONFIRMATION_CONFIDENCE_THRESHOLD,
    CONFIRMATION_FRESH_FRAMES_TO_CHECK,
    CONFIRMATION_REQUIRED_POSITIVE_FRAMES,
    CONFIRMATION_TIMEOUT_SECONDS,
    POST_ALERT_SUPPRESSION_RADIUS_M,
    DetectionSource,
    InvestigationStatus,
    MissionState,
)
from shared.models import DetectionInput, DroneStatus, Position

_ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _detection(detection_id="det-1", confidence=0.9, hazard="fire", source=DetectionSource.PATROL,
               bbox=None, position=None) -> DetectionInput:
    return DetectionInput(
        detection_id=detection_id,
        timestamp="2026-08-15T10:00:00Z",
        hazard=hazard,
        confidence=confidence,
        source=source,
        position=position or Position(0.0, 0.0, 12.0),
        bbox=bbox or [10, 10, 20, 20],
        image_width=CAMERA_WIDTH,
        image_height=CAMERA_HEIGHT,
    )


@pytest.fixture
def controller(tmp_path):
    """A MissionController already in PATROL (main.py's _takeoff() drives
    IDLE->TAKEOFF->PATROL explicitly; tests do the same) with its Logger
    redirected away from the real results/mission_log.jsonl."""
    c = MissionController()
    c.logger.output_path = str(tmp_path / "mission_log.jsonl")
    c.state_machine.transition(MissionState.TAKEOFF)
    c.state_machine.transition(MissionState.PATROL)
    return c


def _drone_status(position=None, connected=True) -> DroneStatus:
    return DroneStatus(
        timestamp="2026-08-15T10:00:00Z",
        position=position or Position(0.0, 0.0, 12.0),
        altitude_m=12.0,
        connected=connected,
        armed=True,
        mission_state="PATROL",
    )


# -- handle_detection -------------------------------------------------------

def test_rejects_out_of_range_confidence(controller):
    assert controller.handle_detection(_detection(confidence=1.5)) is False
    assert controller.state_machine.state == MissionState.PATROL


def test_rejects_unknown_hazard(controller):
    assert controller.handle_detection(_detection(hazard="smog")) is False


def test_rejects_wrong_frame_dimensions(controller):
    det = _detection()
    det.image_width = 320
    assert controller.handle_detection(det) is False


def test_investigation_source_never_triggers_via_handle_detection(controller):
    assert controller.handle_detection(_detection(source=DetectionSource.INVESTIGATION)) is False
    assert controller.state_machine.state == MissionState.PATROL


def test_below_candidate_threshold_does_not_trigger(controller):
    assert controller.handle_detection(_detection(confidence=CANDIDATE_TRIGGER_THRESHOLD - 0.01)) is False
    assert controller.state_machine.state == MissionState.PATROL


def test_at_candidate_threshold_triggers_hazard_detected(controller):
    assert controller.handle_detection(_detection(confidence=CANDIDATE_TRIGGER_THRESHOLD)) is True
    assert controller.state_machine.state == MissionState.HAZARD_DETECTED


def test_second_candidate_ignored_while_not_in_patrol(controller):
    controller.handle_detection(_detection(detection_id="det-1"))
    assert controller.state_machine.state == MissionState.HAZARD_DETECTED
    assert controller.handle_detection(_detection(detection_id="det-2")) is False


def test_suppressed_near_last_confirmed_alert(controller):
    controller.handle_detection(_detection())
    controller.start_investigation()
    for i in range(CONFIRMATION_REQUIRED_POSITIVE_FRAMES):
        controller.handle_investigation_observation(
            _detection(detection_id=f"obs-{i}", source=DetectionSource.INVESTIGATION,
                       confidence=CONFIRMATION_CONFIDENCE_THRESHOLD)
        )
    assert controller.state_machine.state == MissionState.CONFIRMED
    controller.resume_patrol()
    assert controller.state_machine.state == MissionState.PATROL

    nearby = Position(POST_ALERT_SUPPRESSION_RADIUS_M - 0.1, 0.0, 12.0)
    assert controller.handle_detection(_detection(detection_id="det-2", position=nearby)) is False
    assert controller.state_machine.state == MissionState.PATROL


# -- handle_detections: grouping and pending-candidate drain -----------------

def test_handle_detections_investigates_highest_confidence_incident_first(controller):
    far_low = _detection(detection_id="low", confidence=0.7, bbox=[0, 0, 10, 10])
    far_high = _detection(detection_id="high", confidence=0.95, bbox=[600, 450, 630, 470])

    triggered = controller.handle_detections([far_low, far_high])

    assert triggered is True
    assert controller.latest_detection.detection_id == "high"
    assert [d.detection_id for d in controller.pending_candidates] == ["low"]


def test_pending_candidates_are_investigated_on_a_later_call(controller):
    far_low = _detection(detection_id="low", confidence=0.7, bbox=[0, 0, 10, 10])
    far_high = _detection(detection_id="high", confidence=0.95, bbox=[600, 450, 630, 470])
    controller.handle_detections([far_low, far_high])
    assert controller.pending_candidates  # sanity: something was stashed

    # Resolve the active investigation and return to PATROL, exactly like
    # main.py's orchestration loop does before the next waypoint.
    controller.start_investigation()
    for i in range(CONFIRMATION_FRESH_FRAMES_TO_CHECK):
        controller.handle_investigation_observation(None)
    assert controller.state_machine.state == MissionState.REJECTED
    controller.resume_patrol()

    # No *new* detections this frame - only the previously-stashed one.
    triggered = controller.handle_detections([])
    assert triggered is True
    assert controller.latest_detection.detection_id == "low"
    assert controller.pending_candidates == []


def test_handle_detections_with_only_stale_pending_and_no_new_detections_returns_false(controller):
    assert controller.handle_detections([]) is False


# -- investigation lifecycle --------------------------------------------------

def test_start_investigation_requires_hazard_detected_state(controller):
    assert controller.start_investigation() is False


def test_start_investigation_opens_active_investigation(controller):
    controller.handle_detection(_detection())
    assert controller.start_investigation() is True
    assert controller.state_machine.state == MissionState.INVESTIGATING
    assert controller.active_investigation is not None
    assert controller.active_investigation.hazard == "fire"


def test_confirms_after_required_positive_frames(controller):
    controller.handle_detection(_detection())
    controller.start_investigation()
    for i in range(CONFIRMATION_REQUIRED_POSITIVE_FRAMES - 1):
        resolved = controller.handle_investigation_observation(
            _detection(detection_id=f"obs-{i}", source=DetectionSource.INVESTIGATION,
                       confidence=CONFIRMATION_CONFIDENCE_THRESHOLD)
        )
        assert resolved is False
    resolved = controller.handle_investigation_observation(
        _detection(detection_id="obs-last", source=DetectionSource.INVESTIGATION,
                   confidence=CONFIRMATION_CONFIDENCE_THRESHOLD)
    )
    assert resolved is True
    assert controller.state_machine.state == MissionState.CONFIRMED
    assert controller.latest_alert is not None
    assert controller.latest_alert.status == "CONFIRMED"


def test_rejects_after_fresh_frames_checked_without_enough_positives(controller):
    controller.handle_detection(_detection())
    controller.start_investigation()
    resolved = False
    for i in range(CONFIRMATION_FRESH_FRAMES_TO_CHECK):
        resolved = controller.handle_investigation_observation(None)
    assert resolved is True
    assert controller.state_machine.state == MissionState.REJECTED
    assert controller.latest_alert is None


def test_wrong_hazard_observation_does_not_count_as_positive(controller):
    controller.handle_detection(_detection(hazard="fire"))
    controller.start_investigation()
    for i in range(CONFIRMATION_FRESH_FRAMES_TO_CHECK):
        resolved = controller.handle_investigation_observation(
            _detection(detection_id=f"obs-{i}", source=DetectionSource.INVESTIGATION,
                       hazard="smoke", confidence=0.99)
        )
    assert resolved is True
    assert controller.state_machine.state == MissionState.REJECTED


def test_invalid_investigation_observation_is_rejected_without_counting(controller):
    controller.handle_detection(_detection())
    controller.start_investigation()
    bad = _detection(source=DetectionSource.INVESTIGATION, confidence=2.0)
    assert controller.handle_investigation_observation(bad) is False
    assert controller.active_investigation.observations_checked == 0


def test_no_active_investigation_observation_is_a_noop(controller):
    assert controller.handle_investigation_observation(None) is False


def test_check_investigation_timeout_forces_reject(controller):
    controller.handle_detection(_detection())
    controller.start_investigation()
    controller.active_investigation.started_at = (
        datetime.now(timezone.utc) - timedelta(seconds=CONFIRMATION_TIMEOUT_SECONDS + 1)
    ).strftime(_ISO_FORMAT)

    assert controller.check_investigation_timeout() is True
    assert controller.state_machine.state == MissionState.REJECTED


def test_check_investigation_timeout_false_before_deadline(controller):
    controller.handle_detection(_detection())
    controller.start_investigation()
    assert controller.check_investigation_timeout() is False
    assert controller.state_machine.state == MissionState.INVESTIGATING


# -- the resume_patrol observability fix --------------------------------------

def test_confirmed_status_is_observable_before_resume_patrol(controller):
    controller.handle_detection(_detection())
    controller.start_investigation()
    for i in range(CONFIRMATION_REQUIRED_POSITIVE_FRAMES):
        controller.handle_investigation_observation(
            _detection(detection_id=f"obs-{i}", source=DetectionSource.INVESTIGATION,
                       confidence=CONFIRMATION_CONFIDENCE_THRESHOLD)
        )

    controller.handle_drone_status(_drone_status())
    status = controller.get_dashboard_status()
    assert status.mission_state == MissionState.CONFIRMED
    assert status.investigation_status == InvestigationStatus.CONFIRMED

    controller.resume_patrol()
    status = controller.get_dashboard_status()
    assert status.mission_state == MissionState.PATROL
    assert status.investigation_status == InvestigationStatus.IDLE


def test_rejected_status_is_observable_before_resume_patrol(controller):
    controller.handle_detection(_detection())
    controller.start_investigation()
    for _ in range(CONFIRMATION_FRESH_FRAMES_TO_CHECK):
        controller.handle_investigation_observation(None)

    controller.handle_drone_status(_drone_status())
    status = controller.get_dashboard_status()
    assert status.mission_state == MissionState.REJECTED
    assert status.investigation_status == InvestigationStatus.REJECTED

    controller.resume_patrol()
    assert controller.get_dashboard_status().mission_state == MissionState.PATROL


def test_resume_patrol_is_a_noop_outside_confirmed_or_rejected(controller):
    assert controller.resume_patrol() is False
    assert controller.state_machine.state == MissionState.PATROL


# -- drone status / dashboard snapshot ----------------------------------------

def test_dashboard_status_is_none_before_any_drone_status(controller):
    assert controller.get_dashboard_status() is None


def test_disconnect_forces_error_state(controller):
    assert controller.handle_drone_status(_drone_status(connected=False)) is True
    assert controller.state_machine.state == MissionState.ERROR


def test_evidence_image_path_prefers_alert_over_detection(controller):
    det = _detection()
    det.image_path = "results/images/detection.jpg"
    controller.handle_detection(det)
    controller.start_investigation()
    for i in range(CONFIRMATION_REQUIRED_POSITIVE_FRAMES):
        obs = _detection(detection_id=f"obs-{i}", source=DetectionSource.INVESTIGATION,
                          confidence=CONFIRMATION_CONFIDENCE_THRESHOLD)
        obs.image_path = "results/images/investigation.jpg"
        controller.handle_investigation_observation(obs)

    controller.latest_alert.evidence_image_path = "results/images/alert.jpg"
    assert controller._evidence_image_path() == "results/images/alert.jpg"
