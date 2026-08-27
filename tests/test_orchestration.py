"""Integration tests for main.py's OrchestrationMission, driven entirely with
fakes for drone/ and ai/ (per shared/interfaces.py's DetectorProtocol /
DroneProtocol) so no Webots session or trained model is required.
"""
from types import SimpleNamespace

import pytest

from backend.controller import MissionController
from main import OrchestrationMission
from shared.constants import CAMERA_HEIGHT, CAMERA_WIDTH, MissionState


class FakeCamera:
    def __init__(self):
        self.frame_count = 0

    def capture_frame_metadata(self, position):
        self.frame_count += 1
        metadata = SimpleNamespace(
            frame_id=f"frame-{self.frame_count}",
            timestamp="2026-08-15T10:00:00Z",
        )
        return "FAKE_FRAME", metadata


class FakeDrone:
    """Minimal stand-in for drone/drone_controller.py's DroneController."""

    def __init__(self, move_to_failures=(), takeoff_fails=False, land_fails=False):
        self.connected = False
        self.armed = False
        self.camera = FakeCamera()
        self._position = (0.0, 0.0, 0.0)
        self.move_to_failures = set(move_to_failures)
        self.takeoff_fails = takeoff_fails
        self.land_fails = land_fails
        self.move_to_calls = []
        self.investigate_calls = []

    def connect(self):
        self.connected = True
        return self._position

    def arm(self):
        self.armed = True

    def get_position(self):
        return self._position

    def get_heading(self):
        return 0.0

    def takeoff(self, altitude, max_steps):
        if self.takeoff_fails:
            raise RuntimeError("fake takeoff failure")
        self._position = (self._position[0], self._position[1], altitude)
        return self._position

    def move_to(self, x, y, z, max_steps):
        self.move_to_calls.append((x, y, z))
        if (x, y, z) in self.move_to_failures:
            raise RuntimeError("fake move_to failure")
        self._position = (x, y, z)
        return self._position

    def investigate(self, target_hint=None, max_steps=None):
        self.investigate_calls.append(target_hint)
        return self._position

    def land(self, max_steps):
        if self.land_fails:
            raise RuntimeError("fake land failure")
        self._position = (self._position[0], self._position[1], 0.0)
        return self._position

    def disconnect(self):
        self.connected = False


class FakeDetector:
    """Returns one scripted batch of raw detection dicts per detect() call
    (by call order); the last scripted batch repeats once exhausted."""

    def __init__(self, responses):
        self.responses = responses
        self.calls = 0

    def detect(self, frame, frame_id, timestamp, source="patrol", save_evidence=False):
        index = min(self.calls, len(self.responses) - 1)
        batch = self.responses[index]
        self.calls += 1
        return [
            {
                "detection_id": f"det-{self.calls}-{i}",
                "frame_id": frame_id,
                "timestamp": timestamp,
                "hazard": raw.get("hazard", "fire"),
                "confidence": raw["confidence"],
                "bbox": raw.get("bbox", [10, 10, 20, 20]),
                "image_width": CAMERA_WIDTH,
                "image_height": CAMERA_HEIGHT,
                "image_path": None,
                "source": source,
            }
            for i, raw in enumerate(batch)
        ]


TWO_WAYPOINTS = [
    {"name": "wp0", "position": (5, 0, 12.0)},
    {"name": "wp1", "position": (10, 0, 12.0)},
]


@pytest.fixture
def controller(tmp_path):
    c = MissionController()
    c.logger.output_path = str(tmp_path / "mission_log.jsonl")
    return c


def _mission(drone, detector, controller, waypoints=TWO_WAYPOINTS):
    return OrchestrationMission(drone=drone, detector=detector, controller=controller, waypoints=waypoints)


# -- happy path: confirmed alert -----------------------------------------

def test_happy_path_confirms_and_completes_mission(controller):
    drone = FakeDrone()
    detector = FakeDetector([
        [{"confidence": 0.9}],   # wp0 patrol frame: triggers investigation
        [{"confidence": 0.9}],   # investigation frame 1
        [{"confidence": 0.9}],   # investigation frame 2
        [{"confidence": 0.9}],   # investigation frame 3 -> CONFIRMED
        [],                      # wp1 patrol frame: nothing
    ])

    _mission(drone, detector, controller).run()

    assert len(controller.alert_manager.alert_history) == 1
    assert controller.alert_manager.alert_history[0].status == "CONFIRMED"
    assert controller.state_machine.state == MissionState.LANDED
    assert drone.connected is False  # disconnected in main.run()'s finally


# -- all-reject scenario ---------------------------------------------------

def test_all_reject_scenario_creates_no_alert_and_still_completes(controller):
    drone = FakeDrone()
    detector = FakeDetector([
        [{"confidence": 0.9}],  # wp0 patrol frame: triggers investigation
        [], [], [], [],         # 5 empty investigation frames -> REJECTED
        [],                     # wp1 patrol frame: nothing
    ])

    _mission(drone, detector, controller).run()

    assert controller.alert_manager.alert_history == []
    assert controller.state_machine.state == MissionState.LANDED


# -- multi-detection reduction: one investigation frame, several raw boxes --

def test_investigation_frame_reduces_multiple_boxes_to_one_observation(controller):
    drone = FakeDrone()
    # Each investigation frame reports 2 raw boxes; only the higher-confidence
    # one should count as that frame's single observation, so exactly 3
    # investigation frames (not fewer, not requiring all 5) should CONFIRM.
    two_box_frame = [{"confidence": 0.9}, {"confidence": 0.7}]
    detector = FakeDetector([
        [{"confidence": 0.9}],  # wp0 patrol frame: triggers investigation
        two_box_frame, two_box_frame, two_box_frame,
        [],  # wp1 patrol frame
    ])

    _mission(drone, detector, controller).run()

    assert len(controller.alert_manager.alert_history) == 1
    # 1 wp0 patrol call + exactly 3 investigation calls (confirmed on the 3rd,
    # not needing all 5) + 1 wp1 patrol call.
    assert detector.calls == 5


# -- pending candidates: the lower-priority incident gets investigated later -

def test_pending_candidate_from_multi_incident_frame_is_investigated_next(controller):
    drone = FakeDrone()
    detector = FakeDetector([
        # wp0 patrol frame: two far-apart incidents in one frame.
        [
            {"confidence": 0.7, "bbox": [0, 0, 10, 10]},
            {"confidence": 0.95, "bbox": [600, 450, 630, 470]},
        ],
        [], [], [], [],  # 5 empty investigation frames for the high-confidence one -> REJECTED
        # wp1 patrol frame: nothing new - only the stashed low-confidence
        # candidate should surface here.
        [],
    ])

    _mission(drone, detector, controller).run()

    # No alert (both incidents ultimately rejected), but the second incident
    # must have been picked up - not silently dropped, per
    # shared_policy.simultaneous_detections' "log the others for later
    # investigation."
    assert controller.alert_manager.alert_history == []
    assert drone.investigate_calls  # at least the first incident triggered a maneuver
    assert controller.state_machine.state == MissionState.LANDED


# -- failure handling --------------------------------------------------------

def test_move_to_failure_is_logged_and_mission_continues(controller):
    drone = FakeDrone(move_to_failures={(5, 0, 12.0)})
    detector = FakeDetector([[]])

    _mission(drone, detector, controller).run()

    assert (5, 0, 12.0) in drone.move_to_calls
    assert controller.state_machine.state == MissionState.LANDED


def test_takeoff_failure_forces_error_and_still_disconnects(controller):
    drone = FakeDrone(takeoff_fails=True)
    detector = FakeDetector([[]])

    _mission(drone, detector, controller).run()

    assert controller.state_machine.state == MissionState.ERROR
    assert drone.move_to_calls == []  # never reached the patrol route
    assert drone.connected is False


def test_land_failure_forces_error_and_still_disconnects(controller):
    drone = FakeDrone(land_fails=True)
    detector = FakeDetector([[]])

    _mission(drone, detector, controller).run()

    assert controller.state_machine.state == MissionState.ERROR
    assert drone.connected is False
