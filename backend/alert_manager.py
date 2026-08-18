"""Owns confirmed-alert construction and position-based duplicate suppression.
Config: shared_policy.after_confirmed / shared_policy.duplicate_rule (owner: person_3).
"""
import math
import uuid
from datetime import datetime, timezone
from typing import List

from shared.constants import POST_ALERT_SUPPRESSION_RADIUS_M
from shared.models import AlertOutput, InvestigationResult, Position

_ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime(_ISO_FORMAT)


def _horizontal_distance(a: Position, b: Position) -> float:
    """shared_policy.duplicate_rule: x,y only, ignoring z/altitude - ground location
    determines "same physical fire," not the drone's altitude at capture time."""
    return math.hypot(a.x - b.x, a.y - b.y)


class AlertManager:
    def __init__(self):
        self.alert_history: List[AlertOutput] = []

    def create_alert(self, investigation: InvestigationResult, observed_position: Position) -> AlertOutput:
        """shared_policy.after_confirmed: "Create one alert, log it, command RESUME_PATROL."
        Builds the AlertOutput and records it, which also becomes the new suppression
        anchor for is_suppressed()."""
        alert = AlertOutput(
            alert_id=f"alert-{uuid.uuid4().hex[:8]}",
            investigation_id=investigation.investigation_id,
            detection_id=investigation.detection_id,
            timestamp=_now_iso(),
            hazard=investigation.hazard,
            status="CONFIRMED",  # backend_policy.alerting.status_value
            confidence=investigation.representative_confidence or 0.0,
            observed_position=observed_position,
            evidence_image_path=investigation.evidence_image_path,
        )
        self.alert_history.append(alert)
        return alert

    def is_suppressed(self, candidate_position: Position) -> bool:
        """shared_policy.duplicate_rule (position-based): True if candidate_position is
        within POST_ALERT_SUPPRESSION_RADIUS_M of the most recently confirmed alert's
        observed_position."""
        if not self.alert_history:
            return False
        last_position = self.alert_history[-1].observed_position
        return _horizontal_distance(candidate_position, last_position) <= POST_ALERT_SUPPRESSION_RADIUS_M
