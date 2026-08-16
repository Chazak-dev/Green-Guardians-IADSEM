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
