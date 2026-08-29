"""Dataclass mirrors of the JSON-compatible shapes in
config/Green_Guardians_settings.yaml's `backend_contracts` section.

Field names match the YAML exactly so instances serialize to the same JSON
the config promises, with no translation layer needed.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class Position:
    # Config: drone.coordinate_system - Webots world-frame metres, read from
    # drone/drone_controller.py's GPS device, z positive up. NOT AirSim NED.
    # Used wherever a drone position travels with a message, mirroring
    # backend_contracts.mock_detection_input.position /
    # backend_contracts.alert_output.observed_position /
    # backend_contracts.dashboard_status_output.drone_position.
    x: float
    y: float
    z: float


@dataclass
class DroneStatus:
    # Config: contracts.drone_status (producer: person_2, consumers: [person_3]).
    # Grounded in drone/drone_controller.py's real public surface, not the
    # original aspirational contract:
    #   - position/altitude_m: real, from DroneController.get_position().
    #   - connected/armed: real, mirror DroneController's _connected/_armed flags.
    #   - current_waypoint_index: real, but only meaningful while
    #     drone/mission.py's PatrolMission is running - DroneController itself
    #     has no waypoint concept.
    #   - mission_state: NOT reported by the drone (drone_controller.py has no
    #     concept of it) - filled in by the backend from its own current
    #     MissionState value when this snapshot is built.
    #   - No camera_ok/battery: neither is checked anywhere in drone/, so
    #     including them here would just be fabricated data.
    # Sent: person_2 -> person_3 (mission_state excepted - see above).
    timestamp: str
    position: Position
    altitude_m: float
    connected: bool
    armed: bool
    mission_state: str  # a MissionState value (shared.constants.MissionState)
    current_waypoint_index: Optional[int] = None


@dataclass
class TargetHint:
    # Config: contracts.navigation_command.fields.target_hint.
    # Bbox-based direction hint for the INVESTIGATE command - NOT a claimed
    # GPS location. Lets the drone steer toward where the hazard sits in the
    # frame (e.g. left-of-center -> turn left) without the backend ever
    # inventing a real-world position for it.
    bbox: list[int]  # [x1, y1, x2, y2] xyxy pixels
    image_width: int
    image_height: int


@dataclass
class NavigationCommand:
    # Config: contracts.navigation_command (producer: person_3, consumer: person_2).
    # This is a backend-owned contract - person_3 is the producer, so
    # constructing these is squarely backend work.
    # Sent: person_3 -> person_2.
    command_id: str
    timestamp: str
    command: str  # "INVESTIGATE" | "RESUME_PATROL" | "RETURN_HOME" | "LAND"
    detection_id: Optional[str] = None
    target_hint: Optional[TargetHint] = None


@dataclass
class CameraFrameMetadata:
    # Config: contracts.camera_frame_metadata (producer: person_2, consumers: [person_1, person_3]).
    # Doesn't touch backend directly, but kept in shared/ (not backend/) so
    # Person 1 and Person 2 build against the same definition instead of
    # each inventing their own and drifting apart (communication.rule:
    # "Field names and enum values below must match exactly in every module").
    #
    # Caveat: this is a conceptual bundle, not yet literally how the real
    # code talks today. drone/camera.py's capture_frame() only returns a raw
    # frame - nothing in drone/ currently generates frame_id/timestamp.
    # ai/detector.py's detect(frame, frame_id, timestamp, source, ...) takes
    # frame_id/timestamp as separate arguments and computes width/height
    # itself from frame.shape - it does not consume this object directly,
    # and never touches drone_position at all.
    # Sent: person_2 -> person_1 (and person_3, per consumers).
    frame_id: str
    timestamp: str
    image_width: int
    image_height: int
    drone_position: Position


@dataclass
class DetectionInput:
    # Config: backend_contracts.mock_detection_input (owner: person_3).
    # Person 3's own stand-in for the real detection_event contract
    # (top-level contracts.detection_event, producer: person_1) so the
    # backend can be built and tested before ai/ is actually wired to it.
    # Field names (including bbox/image_width/image_height/image_path) match
    # ai/detector.py's actual output dict, so a real detection can populate
    # this directly once ai/ is wired to backend/.
    # Sent: person_1 -> person_3
    detection_id: str
    timestamp: str
    hazard: str            # "fire" | "smoke"
    confidence: float      # 0.0..1.0
    source: str             # "patrol" | "investigation"
    position: Position       # required - where the drone was for this detection
    bbox: list[int]           # required - [x1, y1, x2, y2] xyxy pixels, hazard's location in the frame
    image_width: int
    image_height: int
    frame_id: Optional[str] = None
    image_path: Optional[str] = None


@dataclass
class InvestigationResult:
    # Config: backend_contracts.investigation_result (owner: person_3).
    # Produced by backend/controller.py's _confirm_investigation() when an
    # INVESTIGATING candidate's observation window closes CONFIRMED; consumed
    # by backend/alert_manager.py's create_alert() to build the AlertOutput.
    # Sent: person_3 -> person_3 (internal backend handoff, not cross-person).
    investigation_id: str
    detection_id: str
    started_at: str
    completed_at: str
    hazard: str              # "fire" | "smoke"
    result: str                # "CONFIRMED" | "REJECTED"
    observations_checked: int
    positive_observations: int
    representative_confidence: Optional[float] = None
    evidence_image_path: Optional[str] = None


@dataclass
class AlertOutput:
    # Config: backend_contracts.alert_output (producer: person_3, consumer: person_4).
    # Created at most once per investigation_id (backend_policy.alerting.duplicate_rule)
    # after a CONFIRMED investigation; this is what feeds the dashboard's
    # confirmed_alert_history.
    # Sent: person_3 -> person_4.
    alert_id: str
    investigation_id: str
    detection_id: str
    timestamp: str
    hazard: str        # "fire" | "smoke"
    status: str          # "CONFIRMED"
    confidence: float
    observed_position: Position  # required - drone position when evidence was captured
    evidence_image_path: Optional[str] = None


@dataclass
class DashboardStatusOutput:
    # Config: backend_contracts.dashboard_status_output (producer: person_3, consumer: person_4).
    # One live snapshot of backend state, polled every dashboard.refresh_seconds
    # (1s) so the dashboard can render mission_state, the drone's current
    # position/altitude, and the latest detection/alert (each of which carries
    # its own position via MockDetectionInput/AlertOutput above).
    # Sent: person_3 -> person_4.
    timestamp: str
    mission_state: str
    drone_position: Position  # required - drone's CURRENT position, not tied to a detection/alert
    altitude_m: float          # required - equals drone_position.z
    backend_available: bool
    live_input_available: bool
    investigation_status: str  # "IDLE" | "ACTIVE" | "CONFIRMED" | "REJECTED"
    latest_detection: Optional[DetectionInput]
    latest_alert: Optional[AlertOutput]
    confirmed_alert_count: int
    # Most relevant image to display: latest_alert.evidence_image_path if a
    # confirmed alert exists, otherwise latest_detection.image_path.
    evidence_image_path: Optional[str] = None
    system_message: Optional[str] = None


@dataclass
class LogEvent:
    # Config: backend_contracts.log_event (owner: person_3).
    # Written to results/mission_log.jsonl by backend/logger.py for every
    # state change, accepted/rejected input, investigation result, alert,
    # and error (logging.record).
    # Sent: person_3 -> person_3 (self; a persisted audit record, not a
    # message to another person).
    event_id: str
    timestamp: str
    event_type: str  # STATE_CHANGE | INPUT_ACCEPTED | INPUT_REJECTED | INVESTIGATION_RESULT | ALERT_CREATED | ERROR | FRAME_PROCESSED
    message: str
    mission_state: str
    detection_id: Optional[str] = None
    investigation_id: Optional[str] = None
    alert_id: Optional[str] = None
    details: Optional[dict] = None
