"""Loads and drives sample_data/scenarios/*.json mock mission scenarios
through a real MissionController, for backend development/demoing without
Webots or a trained YOLO model running. Config: mock_development
(owner: person_3).

Each scenario file is a scripted sequence of DetectionInput-shaped frames.
Replaying one exercises the exact same public API main.py's
OrchestrationMission drives in the real orchestration loop
(handle_detections() -> start_investigation() ->
handle_investigation_observation() per fresh frame -> resume_patrol()), so
scenario data proves out real MissionController behavior rather than a
parallel mock implementation.
"""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.controller import MissionController
from config.paths import SCENARIOS_DIR
from shared.constants import MissionState
from shared.models import DetectionInput, DroneStatus, Position

__all__ = ["SCENARIOS_DIR", "load_scenario", "run_scenario", "discover_scenarios"]

_RESOLVED_STATES = (MissionState.CONFIRMED, MissionState.REJECTED)


def discover_scenarios() -> List[Path]:
    return sorted(SCENARIOS_DIR.glob("*.json"))


def load_scenario(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _detection_from_dict(data: Dict[str, Any]) -> DetectionInput:
    fields = dict(data)
    fields["position"] = Position(**fields["position"])
    return DetectionInput(**fields)


def run_scenario(path: Path, controller: Optional[MissionController] = None) -> Dict[str, Any]:
    """Drive one scenario file's steps through `controller` (a fresh
    MissionController by default). Returns a summary dict comparable against
    the scenario's own declared `expected_outcome`.
    """
    scenario = load_scenario(path)
    controller = controller or MissionController()

    # IDLE -> TAKEOFF -> PATROL, matching main.py's _takeoff(): handle_detection()
    # only accepts patrol-phase candidates while the state machine is in PATROL.
    controller.state_machine.transition(MissionState.TAKEOFF)
    controller.state_machine.transition(MissionState.PATROL)

    start_position = scenario.get("drone_start_position", {"x": 0.0, "y": 0.0, "z": 12.0})
    controller.handle_drone_status(DroneStatus(
        timestamp="2026-01-01T00:00:00Z",
        position=Position(**start_position),
        altitude_m=start_position["z"],
        connected=True,
        armed=True,
        mission_state=controller.state_machine.state,
    ))

    triggered = False
    for step in scenario["steps"]:
        phase = step["phase"]
        if phase == "patrol":
            detections = [_detection_from_dict(d) for d in step["detections"]]
            if controller.handle_detections(detections):
                triggered = True
                controller.start_investigation()
        elif phase == "investigation":
            detection = _detection_from_dict(step["detection"]) if step.get("detection") else None
            controller.handle_investigation_observation(detection)
        else:
            raise ValueError(f"Unknown scenario step phase: {phase!r}")

    if controller.active_investigation is not None:
        raise AssertionError(
            f"Scenario {scenario.get('name', path.name)!r} left an investigation "
            "unresolved - add more investigation-phase steps (up to "
            "CONFIRMATION_FRESH_FRAMES_TO_CHECK) so it resolves within its scripted frames."
        )

    resolved_state = controller.state_machine.state
    investigation_result = resolved_state if resolved_state in _RESOLVED_STATES else None
    if investigation_result is not None:
        controller.resume_patrol()

    return {
        "scenario": scenario.get("name", path.stem),
        "investigation_triggered": triggered,
        "investigation_result": investigation_result,
        "final_mission_state": controller.state_machine.state,
        "alert_created": controller.latest_alert is not None,
        "confirmed_alert_count": len(controller.alert_manager.alert_history),
    }
