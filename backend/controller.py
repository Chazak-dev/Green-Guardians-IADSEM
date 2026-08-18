"""Mission controller: the reactive brain that receives inputs, applies
decision policy, and drives the state machine. Config: mission_controller
(owner: person_3).

No loop lives here - something else (main.py, eventually) is responsible
for repeatedly pulling from ai/ and drone/ and calling these methods, and
for periodically calling check_investigation_timeout(). This class only
reacts to whatever it's handed, one call at a time, which keeps it
trivially testable without any real AI/drone connection.

BE-06's AlertManager (backend/alert_manager.py) owns alert construction and
duplicate suppression. BE-07 (logger) doesn't exist yet - see the TODO
markers below for where that plugs in once it does.
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from backend.alert_manager import AlertManager
from backend.state_machine import MissionStateMachine
from shared.constants import (
    CAMERA_HEIGHT,
    CAMERA_WIDTH,
    CANDIDATE_TRIGGER_THRESHOLD,
    CONFIRMATION_CONFIDENCE_THRESHOLD,
    CONFIRMATION_FRESH_FRAMES_TO_CHECK,
    CONFIRMATION_REQUIRED_POSITIVE_FRAMES,
    CONFIRMATION_TIMEOUT_SECONDS,
    DetectionSource,
    Hazard,
    InvestigationOutcome,
    InvestigationStatus,
    MissionState,
)
from shared.models import (
    AlertOutput,
    DashboardStatusOutput,
    DetectionInput,
    DroneStatus,
    InvestigationResult,
)

_INVESTIGATION_STATUS_BY_MISSION_STATE = {
    MissionState.HAZARD_DETECTED: InvestigationStatus.ACTIVE,
    MissionState.INVESTIGATING: InvestigationStatus.ACTIVE,
    MissionState.CONFIRMED: InvestigationStatus.CONFIRMED,
    MissionState.REJECTED: InvestigationStatus.REJECTED,
}

# shared_policy.simultaneous_detections.distance_method: "3x3 image-region rule".
_REGION_GRID_SIZE = 3


_ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime(_ISO_FORMAT)


def _parse_iso(timestamp: str) -> datetime:
    return datetime.strptime(timestamp, _ISO_FORMAT).replace(tzinfo=timezone.utc)


@dataclass
class _ActiveInvestigation:
    """Working state for the investigation currently in progress. Not a
    shared/models.py contract - this is purely internal book-keeping while
    shared_policy.confirmation's window is still open."""
    investigation_id: str
    detection_id: str
    hazard: str
    started_at: str  # ISO-8601 UTC
    observations_checked: int = 0
    positive_observations: int = 0
    representative_confidence: float = 0.0


def _bbox_region(bbox: List[int], image_width: int, image_height: int) -> tuple:
    """Which of the 3x3 grid cells the bbox's center falls in, as (row, col)."""
    x1, y1, x2, y2 = bbox
    center_x, center_y = (x1 + x2) / 2, (y1 + y2) / 2
    col = min(int(center_x / image_width * _REGION_GRID_SIZE), _REGION_GRID_SIZE - 1)
    row = min(int(center_y / image_height * _REGION_GRID_SIZE), _REGION_GRID_SIZE - 1)
    return (row, col)


def _bboxes_overlap(bbox_a: List[int], bbox_b: List[int]) -> bool:
    ax1, ay1, ax2, ay2 = bbox_a
    bx1, by1, bx2, by2 = bbox_b
    return not (ax2 < bx1 or bx2 < ax1 or ay2 < by1 or by2 < ay1)


def _not_far_apart(a: DetectionInput, b: DetectionInput) -> bool:
    """shared_policy.simultaneous_detections: same region -> not far apart;
    neighboring regions -> only if bboxes overlap; otherwise far apart."""
    region_a = _bbox_region(a.bbox, a.image_width, a.image_height)
    region_b = _bbox_region(b.bbox, b.image_width, b.image_height)
    grid_distance = max(abs(region_a[0] - region_b[0]), abs(region_a[1] - region_b[1]))
    if grid_distance == 0:
        return True
    if grid_distance == 1:
        return _bboxes_overlap(a.bbox, b.bbox)
    return False


def _group_into_incidents(detections: List[DetectionInput]) -> List[List[DetectionInput]]:
    """Connected-components grouping by _not_far_apart, so a chain of pairwise
    'not far apart' detections ends up in one incident even if the first and
    last aren't directly close - a single greedy pass can miss that."""
    groups = [[d] for d in detections]
    merged = True
    while merged:
        merged = False
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                if any(_not_far_apart(a, b) for a in groups[i] for b in groups[j]):
                    groups[i].extend(groups.pop(j))
                    merged = True
                    break
            if merged:
                break
    return groups


class MissionController:
    def __init__(self):
        self.state_machine = MissionStateMachine()
        self.latest_detection: Optional[DetectionInput] = None
        self.latest_drone_status: Optional[DroneStatus] = None
        self.alert_manager = AlertManager()
        self.latest_alert: Optional[AlertOutput] = None
        self.pending_candidates: List[DetectionInput] = []  # lower-priority incidents from handle_detections()
        self.active_investigation: Optional[_ActiveInvestigation] = None

    def handle_detections(self, detections: List[DetectionInput]) -> bool:
        """Process every detection from one frame at once. Groups simultaneous
        candidates into incidents (shared_policy.simultaneous_detections),
        investigates the highest-confidence incident first via
        handle_detection(), and stashes the rest in pending_candidates.
        Returns whether the top incident triggered a state change."""
        valid = [d for d in detections if self._is_valid_detection(d)]
        # TODO(BE-07): log the dropped ones as INPUT_REJECTED

        investigation_phase = [d for d in valid if d.source != DetectionSource.PATROL]
        for det in investigation_phase:
            self.handle_investigation_observation(det)  # no grouping - not competing for "investigate first"

        patrol_phase = [d for d in valid if d.source == DetectionSource.PATROL]
        if not patrol_phase:
            return False

        incidents = _group_into_incidents(patrol_phase)
        representatives = sorted(
            (max(group, key=lambda d: d.confidence) for group in incidents),
            key=lambda d: d.confidence,
            reverse=True,
        ) 

        triggered = self.handle_detection(representatives[0])
        self.pending_candidates = representatives[1:]
        # TODO(BE-07): log pending_candidates as logged-for-later
        return triggered
    
    def start_investigation(self) -> bool:
        """Move HAZARD_DETECTED -> INVESTIGATING and open a confirmation
        window for the current candidate. Nothing calls this yet: the real
        trigger should be the drone confirming it has begun the investigation
        maneuver, and drone/ doesn't implement that maneuver yet (config:
        drone.investigation_maneuver.status: not_yet_implemented). This
        exists so BE-09 has something ready to call once it does."""
        if not self.state_machine.transition(MissionState.INVESTIGATING):
            return False
        self.active_investigation = _ActiveInvestigation(
            investigation_id=f"inv-{uuid.uuid4().hex[:8]}",
            detection_id=self.latest_detection.detection_id,
            hazard=self.latest_detection.hazard,
            started_at=_now_iso(),
        )
        return True

    def handle_investigation_observation(self, detection: DetectionInput) -> bool:
        """Process one fresh investigation-phase frame against the active
        investigation's confirmation window (shared_policy.confirmation).
        Returns whether it resolved the investigation (CONFIRMED/REJECTED)."""
        if self.active_investigation is None or self.state_machine.state != MissionState.INVESTIGATING:
            return False  # nothing active to check this against

        if not self._is_valid_detection(detection):
            return False  # TODO(BE-07): log as INPUT_REJECTED

        self.latest_detection = detection

        inv = self.active_investigation
        inv.observations_checked += 1
        # same_hazard_required: true - must match the ORIGINAL candidate's hazard.
        is_positive = (
            detection.hazard == inv.hazard
            and detection.confidence >= CONFIRMATION_CONFIDENCE_THRESHOLD
        )
        if is_positive:
            inv.positive_observations += 1
            inv.representative_confidence = max(inv.representative_confidence, detection.confidence)

        if inv.positive_observations >= CONFIRMATION_REQUIRED_POSITIVE_FRAMES:
            return self._confirm_investigation()
        if inv.observations_checked >= CONFIRMATION_FRESH_FRAMES_TO_CHECK:
            return self._reject_investigation()
        return False  # still collecting evidence

    def check_investigation_timeout(self) -> bool:
        """Call periodically from the orchestration loop. Forces REJECTED if
        the active investigation has run past CONFIRMATION_TIMEOUT_SECONDS
        with no resolution - the only way this reactive controller can notice
        time passing when no new frames are arriving at all."""
        if self.active_investigation is None:
            return False
        elapsed = (datetime.now(timezone.utc) - _parse_iso(self.active_investigation.started_at)).total_seconds()
        if elapsed < CONFIRMATION_TIMEOUT_SECONDS:
            return False
        return self._reject_investigation()

    def _confirm_investigation(self) -> bool:
        inv = self.active_investigation
        observed_position = (
            self.latest_drone_status.position
            if self.latest_drone_status is not None
            else self.latest_detection.position
        )
        self.state_machine.transition(MissionState.CONFIRMED)
        investigation_result = InvestigationResult(
            investigation_id=inv.investigation_id,
            detection_id=inv.detection_id,
            started_at=inv.started_at,
            completed_at=_now_iso(),
            hazard=inv.hazard,
            result=InvestigationOutcome.CONFIRMED,
            observations_checked=inv.observations_checked,
            positive_observations=inv.positive_observations,
            representative_confidence=inv.representative_confidence,
            evidence_image_path=self.latest_detection.image_path,
        )
        self.latest_alert = self.alert_manager.create_alert(investigation_result, observed_position)
        self.state_machine.transition(MissionState.PATROL)
        self.active_investigation = None
        return True
        # TODO(BE-07): log INVESTIGATION_RESULT and ALERT_CREATED

    def _reject_investigation(self) -> bool:
        self.state_machine.transition(MissionState.REJECTED)
        self.state_machine.transition(MissionState.PATROL)
        self.active_investigation = None
        return True
        # TODO(BE-07): log INVESTIGATION_RESULT (no alert created)

    def handle_detection(self, detection: DetectionInput) -> bool:
        """Process a new detection. Returns whether it triggered a state change."""
        # backend_policy.failure_handling.malformed_input: reject and keep running
        if not self._is_valid_detection(detection):
            return False  # TODO(BE-07): log as INPUT_REJECTED

        self.latest_detection = detection

        # Investigation-phase frames feed the confirmation rule (BE-04), not this.
        if detection.source != DetectionSource.PATROL:
            return False

        # mission_controller.rules: "Only one investigation may be active at a time."
        if self.state_machine.state != MissionState.PATROL:
            return False

        # shared_policy.duplicate_rule: within the suppression radius of the last
        # confirmed alert's observed_position, treat this as the same physical fire.
        if self.alert_manager.is_suppressed(detection.position):
            return False  # TODO(BE-07): log distinctly from a low-confidence rejection

        # shared_policy.candidate_trigger: confidence >= 0.60 during PATROL.
        if detection.confidence < CANDIDATE_TRIGGER_THRESHOLD:
            return False

        return self.state_machine.transition(MissionState.HAZARD_DETECTED)
        # TODO(BE-07): log as INPUT_ACCEPTED / STATE_CHANGE

    def handle_drone_status(self, status: DroneStatus) -> bool:
        """Record the drone's latest status. Returns whether it forced a state change."""
        self.latest_drone_status = status
    
        if not status.connected:
            return self.state_machine.transition(MissionState.ERROR)
            # TODO(BE-07): log as ERROR if this actually changed state

        return False

    def get_dashboard_status(self) -> Optional[DashboardStatusOutput]:
        """Assemble a snapshot for Person 4. Returns None until a drone status
        has been received at least once - there's no honest drone_position to
        report before that."""
        if self.latest_drone_status is None:
            return None
    
        return DashboardStatusOutput(
            timestamp=_now_iso(),
            mission_state=self.state_machine.state,
            drone_position=self.latest_drone_status.position,
            altitude_m=self.latest_drone_status.altitude_m,
            backend_available=True,
            live_input_available=False,  # TODO(BE-08/BE-09): flip once real ai/drone integration exists
            investigation_status=_INVESTIGATION_STATUS_BY_MISSION_STATE.get(
                self.state_machine.state, InvestigationStatus.IDLE
            ),
            latest_detection=self.latest_detection,
            latest_alert=self.latest_alert,
            confirmed_alert_count=len(self.alert_manager.alert_history),
            evidence_image_path=self._evidence_image_path(),
        )

    def _evidence_image_path(self) -> Optional[str]:
        if self.latest_alert and self.latest_alert.evidence_image_path:
            return self.latest_alert.evidence_image_path
        if self.latest_detection and self.latest_detection.image_path:
            return self.latest_detection.image_path
        return None

    @staticmethod
    def _is_valid_detection(detection: DetectionInput) -> bool:
        if not (0.0 <= detection.confidence <= 1.0):
            return False
        if detection.hazard not in (Hazard.FIRE, Hazard.SMOKE):
            return False
        if detection.image_width != CAMERA_WIDTH or detection.image_height != CAMERA_HEIGHT:
            return False
        return True
