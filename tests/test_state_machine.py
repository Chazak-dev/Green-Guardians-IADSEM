from backend.state_machine import MissionStateMachine
from shared.constants import MissionState


def test_initial_state_is_idle():
    assert MissionStateMachine().state == MissionState.IDLE


def test_normal_flow_happy_path():
    sm = MissionStateMachine()
    happy_path = [
        MissionState.TAKEOFF,
        MissionState.PATROL,
        MissionState.HAZARD_DETECTED,
        MissionState.INVESTIGATING,
        MissionState.CONFIRMED,
        MissionState.PATROL,
        MissionState.RETURN_HOME,
        MissionState.LANDING,
        MissionState.LANDED,
    ]
    for target in happy_path:
        assert sm.transition(target) is True
        assert sm.state == target


def test_rejected_path_returns_to_patrol():
    sm = MissionStateMachine()
    for target in (MissionState.TAKEOFF, MissionState.PATROL, MissionState.HAZARD_DETECTED,
                   MissionState.INVESTIGATING, MissionState.REJECTED, MissionState.PATROL):
        assert sm.transition(target)


def test_invalid_transition_is_rejected_and_state_unchanged():
    sm = MissionStateMachine()
    assert sm.can_transition(MissionState.PATROL) is False
    assert sm.transition(MissionState.PATROL) is False
    assert sm.state == MissionState.IDLE


def test_landed_is_a_dead_end():
    sm = MissionStateMachine()
    for target in (MissionState.TAKEOFF, MissionState.PATROL, MissionState.RETURN_HOME,
                   MissionState.LANDING, MissionState.LANDED):
        sm.transition(target)
    assert sm.state == MissionState.LANDED
    for target in MissionState:
        assert sm.can_transition(target) is False


def test_error_is_recoverable_to_idle():
    sm = MissionStateMachine()
    sm.transition(MissionState.TAKEOFF)
    assert sm.transition(MissionState.ERROR)
    assert sm.transition(MissionState.IDLE)


def test_patrol_can_go_straight_to_return_home():
    sm = MissionStateMachine()
    sm.transition(MissionState.TAKEOFF)
    sm.transition(MissionState.PATROL)
    assert sm.transition(MissionState.RETURN_HOME)
