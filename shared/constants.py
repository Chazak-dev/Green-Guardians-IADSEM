"""Enum mirrors of the allowed string values in
config/Green_Guardians_settings.yaml's mission_controller and
backend_contracts sections.

StrEnum members are strings, so they compare equal to and serialize as the
plain values the config/JSON contracts expect (e.g. MissionState.PATROL ==
"PATROL"), with no .value conversion needed in shared/models.py or JSON output.
"""
from enum import StrEnum

# Config: camera.width / camera.height - expected frame dimensions from
# drone/camera.py's Webots camera device. Use these to sanity-check incoming
# DetectionInput.image_width/image_height rather than trusting them blindly.
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480

# Config: shared_policy.candidate_trigger.threshold - during PATROL, a
# fire/smoke detection at or above this confidence creates a candidate and
# triggers investigation.
CANDIDATE_TRIGGER_THRESHOLD = 0.60

# Config: shared_policy.confirmation - while INVESTIGATING, check fresh
# investigation-source frames against these thresholds to decide
# CONFIRMED vs REJECTED.
CONFIRMATION_FRESH_FRAMES_TO_CHECK = 5
CONFIRMATION_REQUIRED_POSITIVE_FRAMES = 3
CONFIRMATION_CONFIDENCE_THRESHOLD = 0.65
CONFIRMATION_TIMEOUT_SECONDS = 15

# Config: shared_policy.post_alert_suppression_radius_m / duplicate_rule - after a
# confirmed alert, suppress new PATROL-phase candidates within this many horizontal
# (x,y) metres of that alert's observed_position: probably the same physical fire, not
# a new one. Replaces an earlier time-based number (post_alert_suppression_seconds: 8)
# that assumed AirSim-era constant patrol speed and 15m waypoint spacing - the real
# drone has no constant commanded speed (drone.flight_control is a PID stabilization
# loop), so travel time is not a reliable "same location" proxy; distance is.
POST_ALERT_SUPPRESSION_RADIUS_M = 5.0

# Config: logging.output_path - JSONL file backend/logger.py appends one
# LogEvent per line to.
LOG_OUTPUT_PATH = "results/mission_log.jsonl"


class MissionState(StrEnum):
    # Config: mission_controller.states
    IDLE = "IDLE"
    TAKEOFF = "TAKEOFF"
    PATROL = "PATROL"
    HAZARD_DETECTED = "HAZARD_DETECTED"
    INVESTIGATING = "INVESTIGATING"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    RETURN_HOME = "RETURN_HOME"
    LANDING = "LANDING"
    LANDED = "LANDED"
    ERROR = "ERROR"


class InvestigationStatus(StrEnum):
    # Config: backend_contracts.dashboard_status_output.required_fields.investigation_status
    IDLE = "IDLE"
    ACTIVE = "ACTIVE"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"


class Hazard(StrEnum):
    # Config: hazard field on mock_detection_input / investigation_result / alert_output
    FIRE = "fire"
    SMOKE = "smoke"


class DetectionSource(StrEnum):
    # Config: backend_contracts.mock_detection_input.required_fields.source
    PATROL = "patrol"
    INVESTIGATION = "investigation"


class InvestigationOutcome(StrEnum):
    # Config: backend_contracts.investigation_result.required_fields.result
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"


class LogEventType(StrEnum):
    # Config: backend_contracts.log_event.required_fields.event_type
    STATE_CHANGE = "STATE_CHANGE"
    INPUT_ACCEPTED = "INPUT_ACCEPTED"
    INPUT_REJECTED = "INPUT_REJECTED"
    INVESTIGATION_RESULT = "INVESTIGATION_RESULT"
    ALERT_CREATED = "ALERT_CREATED"
    ERROR = "ERROR"
