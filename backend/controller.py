"""Mission controller: the reactive brain that receives inputs, applies
decision policy, and drives the state machine. Config: mission_controller
(owner: person_3).

No loop lives here - main.py's OrchestrationMission (BE-08/BE-09) is
responsible for repeatedly pulling from ai/ and drone/ and calling these
methods, and for periodically calling check_investigation_timeout(). This
class only reacts to whatever it's handed, one call at a time, which keeps
it trivially testable without any real AI/drone connection.

BE-06's AlertManager (backend/alert_manager.py) owns alert construction and
duplicate suppression. BE-07's Logger (backend/logger.py) owns writing
LogEvent records to results/mission_log.jsonl via the private _log() helper.
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from backend.alert_manager import AlertManager
from backend.logger import Logger
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
    LogEventType,
    MissionState,
)
from shared.models import (
    AlertOutput,
    DashboardStatusOutput,
    DetectionInput,
    DroneStatus,
    InvestigationResult,
    LogEvent,
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
        self.logger = Logger()
        self.pending_candidates: List[DetectionInput] = []  # lower-priority incidents from handle_detections()
        self.active_investigation: Optional[_ActiveInvestigation] = None

    def _log(self, event_type: str, message: str, *, detection_id=None,
             investigation_id=None, alert_id=None, details=None) -> None:
        """logging.record: build a LogEvent from whatever's relevant and append it."""
        self.logger.log(LogEvent(
            event_id=f"event-{uuid.uuid4().hex[:8]}",
            timestamp=_now_iso(),
            event_type=event_type,
            message=message,
            mission_state=self.state_machine.state,
            detection_id=detection_id,
            investigation_id=investigation_id,
            alert_id=alert_id,
            details=details,
        ))

    def handle_detections(self, detections: List[DetectionInput]) -> bool:
        """Process every detection from one frame at once. Groups simultaneous
        candidates into incidents (shared_policy.simultaneous_detections),
        investigates the highest-confidence incident first via
        handle_detection(), and stashes the rest in pending_candidates so a
        later call - once the current investigation has resolved - gets a
        chance to actually investigate them, per
        shared_policy.simultaneous_detections: "log the others for later
        investigation." Returns whether the top incident triggered a state
        change."""
        valid = []
        for d in detections:
            if self._is_valid_detection(d):
                valid.append(d)
            else:
                self._log(LogEventType.INPUT_REJECTED, "Detection rejected: invalid fields",
                           detection_id=d.detection_id)

        investigation_phase = [d for d in valid if d.source != DetectionSource.PATROL]
        for det in investigation_phase:
            self.handle_investigation_observation(det)  # no grouping - not competing for "investigate first"

        patrol_phase = [d for d in valid if d.source == DetectionSource.PATROL]
        carried_over, self.pending_candidates = self.pending_candidates, []
        candidates = carried_over + patrol_phase
        if not candidates:
            return False

        incidents = _group_into_incidents(candidates)
        representatives = sorted(
            (max(group, key=lambda d: d.confidence) for group in incidents),
            key=lambda d: d.confidence,
            reverse=True,
        )

        triggered = self.handle_detection(representatives[0])
        if triggered:
            self.pending_candidates = representatives[1:]
        else:
            # Not just "below threshold" or "suppressed as duplicate" - those
            # are permanent for this candidate and shouldn't be retried. But
            # if handle_detection() declined only because an investigation is
            # already active (mission_controller.rules: "Only one
            # investigation may be active at a time"), the top candidate must
            # stay queued too instead of being silently dropped.
            if self.state_machine.state != MissionState.PATROL:
                self.pending_candidates = representatives
        for pending in self.pending_candidates:
            self._log(LogEventType.INPUT_ACCEPTED, "Lower-priority candidate logged for later investigation",
                       detection_id=pending.detection_id, details={"status": "pending"})
        return triggered
    
    def start_investigation(self) -> bool:
        """Move HAZARD_DETECTED -> INVESTIGATING and open a confirmation
        window for the current candidate. Called by main.py's orchestration
        loop (BE-09) right before drone.investigate() physically moves the
        drone (config: drone.investigation_maneuver, implemented)."""
        if not self.state_machine.transition(MissionState.INVESTIGATING):
            return False
        self.active_investigation = _ActiveInvestigation(
            investigation_id=f"inv-{uuid.uuid4().hex[:8]}",
            detection_id=self.latest_detection.detection_id,
            hazard=self.latest_detection.hazard,
            started_at=_now_iso(),
        )
        return True

    def handle_investigation_observation(self, detection: Optional[DetectionInput]) -> bool:
        """Process one fresh investigation-phase frame's outcome
        (shared_policy.confirmation). `detection` is None when ai/detector.py's
        detect() saw nothing this frame - that's a real, countable non-positive
        check, not invalid input to be skipped or faked: a frame with nothing
        to report is not the same thing as a malformed DetectionInput, and
        skipping it would let a hazard hide by producing empty frames.
        Returns whether it resolved the investigation (CONFIRMED/REJECTED)."""
        if self.active_investigation is None or self.state_machine.state != MissionState.INVESTIGATING:
            return False  # nothing active to check this against

        if detection is not None and not self._is_valid_detection(detection):
            self._log(LogEventType.INPUT_REJECTED, "Investigation observation rejected: invalid fields",
                       detection_id=detection.detection_id,
                       investigation_id=self.active_investigation.investigation_id)
            return False

        inv = self.active_investigation
        inv.observations_checked += 1

        if detection is not None:
            self.latest_detection = detection
            # same_hazard_required: true - must match the ORIGINAL candidate's hazard.
            is_positive = (
                detection.hazard == inv.hazard
                and detection.confidence >= CONFIRMATION_CONFIDENCE_THRESHOLD
            )
            if is_positive:
                inv.positive_observations += 1
                inv.representative_confidence = max(inv.representative_confidence, detection.confidence)
        else:
            self._log(LogEventType.INPUT_ACCEPTED, "Investigation frame checked: no hazard observed",
                       investigation_id=inv.investigation_id,
                       details={"observations_checked": inv.observations_checked})

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
        self._log(LogEventType.INVESTIGATION_RESULT, f"Investigation {inv.investigation_id} CONFIRMED",
                   investigation_id=inv.investigation_id, detection_id=inv.detection_id)
        self._log(LogEventType.ALERT_CREATED, f"Confirmed {inv.hazard} alert created",
                   investigation_id=inv.investigation_id, alert_id=self.latest_alert.alert_id)
        self.active_investigation = None
        return True

    def _reject_investigation(self) -> bool:
        inv = self.active_investigation
        self.state_machine.transition(MissionState.REJECTED)
        self._log(LogEventType.INVESTIGATION_RESULT, f"Investigation {inv.investigation_id} REJECTED",
                   investigation_id=inv.investigation_id, detection_id=inv.detection_id)
        self.active_investigation = None
        return True

    def resume_patrol(self) -> bool:
        """shared_policy.after_confirmed/after_rejected's explicit "command
        RESUME_PATROL" step: moves CONFIRMED/REJECTED back to PATROL.

        Deliberately NOT called from _confirm_investigation()/_reject_investigation()
        themselves - folding it in there meant the state machine passed through
        CONFIRMED/REJECTED and back to PATROL within a single synchronous call,
        so nothing (e.g. main.py's orchestration loop reporting a status snapshot
        to the dashboard) could ever observe investigation_status CONFIRMED/
        REJECTED; get_dashboard_status() always saw PATROL/IDLE instead. Callers
        must invoke this explicitly once they're done observing the resolved
        investigation, per config's shared_policy.after_confirmed /
        after_rejected."""
        prior_state = self.state_machine.state
        changed = self.state_machine.transition(MissionState.PATROL)
        if changed:
            self._log(LogEventType.STATE_CHANGE, f"{prior_state} -> PATROL")
        return changed

    def handle_detection(self, detection: DetectionInput) -> bool:
        """Process a new detection. Returns whether it triggered a state change."""
        # backend_policy.failure_handling.malformed_input: reject and keep running
        if not self._is_valid_detection(detection):
            self._log(LogEventType.INPUT_REJECTED, "Detection rejected: invalid fields",
                       detection_id=detection.detection_id)
            return False

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
            self._log(LogEventType.INPUT_REJECTED, "Detection rejected: suppressed as duplicate of recent alert",
                       detection_id=detection.detection_id)
            return False

        # shared_policy.candidate_trigger: confidence >= 0.60 during PATROL.
        if detection.confidence < CANDIDATE_TRIGGER_THRESHOLD:
            return False

        triggered = self.state_machine.transition(MissionState.HAZARD_DETECTED)
        if triggered:
            self._log(LogEventType.INPUT_ACCEPTED, f"Detection accepted as candidate (hazard={detection.hazard})",
                       detection_id=detection.detection_id)
            self._log(LogEventType.STATE_CHANGE, "PATROL -> HAZARD_DETECTED", detection_id=detection.detection_id)
        return triggered

    def handle_drone_status(self, status: DroneStatus) -> bool:
        """Record the drone's latest status. Returns whether it forced a state change."""
        self.latest_drone_status = status
    
        if not status.connected:
            changed = self.state_machine.transition(MissionState.ERROR)
            if changed:
                self._log(LogEventType.ERROR, "Drone disconnected, forcing ERROR state")
            return changed

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
