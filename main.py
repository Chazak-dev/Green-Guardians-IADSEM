"""Application entry point: the live orchestration loop tying drone/, ai/,
and backend/ together into one running mission. Config: files_and_folders.main_py
("Person 3-led application entry point"). This is the piece
shared_policy.after_confirmed and drone.investigation_maneuver both call out
as needing (BE-08/BE-09).

Reuses drone/mission.py's PATROL_ROUTE/WAYPOINT_MAX_STEPS rather than
redefining the waypoint list; PatrolMission itself is untouched and keeps
working standalone for basic camera/flight smoke-testing.
"""
from datetime import datetime, timezone
from typing import List, Optional

from ai.detector import FireSmokeDetector
from backend.controller import MissionController
from drone.drone_controller import DroneController
from drone.mission import PATROL_ROUTE, WAYPOINT_MAX_STEPS
from shared.constants import CONFIRMATION_FRESH_FRAMES_TO_CHECK, DetectionSource, MissionState
from shared.models import DetectionInput, DroneStatus, Position, TargetHint

_ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime(_ISO_FORMAT)


class OrchestrationMission:
    def __init__(self, drone=None, detector=None, controller=None, waypoints=None):
        self.drone = drone or DroneController()
        self.detector = detector or FireSmokeDetector()
        self.controller = controller or MissionController()
        self.waypoints = waypoints or PATROL_ROUTE

    def run(self):
        """Full mission lifecycle: mission_controller.normal_flow end-to-end."""
        try:
            if not self._takeoff():
                return  # ERROR already transitioned/logged inside _takeoff
            for index, waypoint in enumerate(self.waypoints):
                self._run_waypoint(index, waypoint)
            self._return_and_land()
        finally:
            self.drone.disconnect()

    def _takeoff(self) -> bool:
        """IDLE -> TAKEOFF -> PATROL. Driven explicitly here - MissionController
        never advances these two phases on its own, only hazard/investigation/
        error transitions are internally driven."""
        self.drone.connect()
        self.drone.arm()
        self.controller.state_machine.transition(MissionState.TAKEOFF)
        self._report_status(waypoint_index=None)
        try:
            self.drone.takeoff(altitude=self.waypoints[0]["position"][2], max_steps=WAYPOINT_MAX_STEPS)
        except RuntimeError as exc:
            print(f"Takeoff failed ({exc}); forcing ERROR - cannot patrol without a confirmed altitude.")
            self.controller.state_machine.transition(MissionState.ERROR)
            return False
        self.controller.state_machine.transition(MissionState.PATROL)
        self._report_status(waypoint_index=None)
        return True

    def _report_status(self, waypoint_index: Optional[int]) -> DroneStatus:
        """contracts.drone_status: mission_state is NOT reported by the drone -
        filled in here from the controller's own current state."""
        x, y, z = self.drone.get_position()
        status = DroneStatus(
            timestamp=_now_iso(), position=Position(x, y, z), altitude_m=z,
            connected=self.drone.connected, armed=self.drone.armed,
            mission_state=self.controller.state_machine.state,
            current_waypoint_index=waypoint_index,
        )
        self.controller.handle_drone_status(status)
        return status

    def _run_waypoint(self, index: int, waypoint: dict) -> None:
        """drone.patrol_route: visit one waypoint, detect, hand off to
        investigation if it triggers HAZARD_DETECTED."""
        name = waypoint["name"]
        x, y, z = waypoint["position"]
        try:
            position = self.drone.move_to(x, y, z, max_steps=WAYPOINT_MAX_STEPS)
        except RuntimeError as exc:
            print(f"Warning: could not reach waypoint {name!r} ({exc}); continuing from current position.")
            position = self.drone.get_position()
        self._report_status(waypoint_index=index)

        detections = self._detect_at(position, f"patrol-{index:02d}-{name}", DetectionSource.PATROL)
        if self.controller.handle_detections(detections):
            self._investigate(index)

    def _detect_at(self, position, frame_label: str, source: str) -> List[DetectionInput]:
        """ai.model_path inference over one captured frame, adapted into
        DetectionInput: field names match ai/detector.py's dict 1:1 except
        `position`, which the AI never produces and this caller must add."""
        frame, metadata = self.drone.camera.capture_frame_metadata(position)
        raw = self.detector.detect(
            frame, frame_id=f"{metadata.frame_id}-{frame_label}", timestamp=metadata.timestamp,
            source=source, save_evidence=True,
        )
        return [DetectionInput(position=Position(*position), **det) for det in raw]

    def _investigate(self, waypoint_index: int) -> None:
        """drone.investigation_maneuver + shared_policy.confirmation: pause,
        nudge toward the triggering detection, then check up to
        CONFIRMATION_FRESH_FRAMES_TO_CHECK fresh frames, resolving early on
        CONFIRMED/REJECTED or on timeout."""
        if not self.controller.start_investigation():
            print("Warning: start_investigation() declined (unexpected state); skipping.")
            return

        triggering = self.controller.latest_detection
        hint = TargetHint(bbox=triggering.bbox, image_width=triggering.image_width,
                           image_height=triggering.image_height)
        # investigate() never raises (falls back to holding in place per its
        # own safety_fallback guarantee) - no try/except needed here.
        position = self.drone.investigate(hint)
        self._report_status(waypoint_index)

        for check_index in range(CONFIRMATION_FRESH_FRAMES_TO_CHECK):
            if self.controller.check_investigation_timeout():
                break
            if self.controller.active_investigation is None:
                break  # resolved already
            label = f"investigation-{waypoint_index:02d}-{check_index}"
            detections = self._detect_at(position, label, DetectionSource.INVESTIGATION)
            # Reduce multiple detections in one frame to the single highest-
            # confidence one - "5 frames checked" means 5 camera frames, not
            # 5 raw boxes (mirrors handle_detections()'s patrol-side reduction).
            representative = max(detections, key=lambda d: d.confidence, default=None)
            if self.controller.handle_investigation_observation(representative):
                break

        self._report_status(waypoint_index)

    def _return_and_land(self) -> None:
        """PATROL -> RETURN_HOME -> LANDING -> LANDED."""
        self.controller.state_machine.transition(MissionState.RETURN_HOME)
        self._report_status(waypoint_index=None)
        self.controller.state_machine.transition(MissionState.LANDING)
        try:
            self.drone.land(max_steps=WAYPOINT_MAX_STEPS)
        except RuntimeError as exc:
            print(f"Warning: land() could not converge ({exc}); forcing ERROR.")
            self.controller.state_machine.transition(MissionState.ERROR)
            return
        self.controller.state_machine.transition(MissionState.LANDED)
        self._report_status(waypoint_index=None)


if __name__ == "__main__":
    OrchestrationMission().run()
