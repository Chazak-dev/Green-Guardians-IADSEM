"""Mission state machine: pure state-transition logic, no side effects.

Config: mission_controller (owner: person_3). Encodes mission_controller.
normal_flow and rules as an explicit transition table, rather than scattering
if/elif checks through the controller.

Logging of rejected transitions is the caller's (backend/controller.py's)
job, not this file's - transition() never raises, it just reports whether
the move was allowed, per mission_controller.rules:
"Invalid input is logged and does not crash the controller."
"""
from shared.constants import MissionState

# mission_controller.normal_flow, plus two decisions confirmed with the team:
# ERROR is recoverable back to IDLE (not a dead end like LANDED), and PATROL
# can go straight to RETURN_HOME (an operator-issued return, not only after
# a CONFIRMED/REJECTED cycle).
TRANSITIONS = {
    MissionState.IDLE: {MissionState.TAKEOFF},
    MissionState.TAKEOFF: {MissionState.PATROL, MissionState.ERROR},
    MissionState.PATROL: {MissionState.HAZARD_DETECTED, MissionState.RETURN_HOME, MissionState.ERROR},
    MissionState.HAZARD_DETECTED: {MissionState.INVESTIGATING, MissionState.ERROR},
    MissionState.INVESTIGATING: {MissionState.CONFIRMED, MissionState.REJECTED, MissionState.ERROR},
    MissionState.CONFIRMED: {MissionState.PATROL},
    MissionState.REJECTED: {MissionState.PATROL},
    MissionState.RETURN_HOME: {MissionState.LANDING, MissionState.ERROR},
    MissionState.LANDING: {MissionState.LANDED, MissionState.ERROR},
    MissionState.LANDED: set(),
    MissionState.ERROR: {MissionState.IDLE},
}


class MissionStateMachine:
    def __init__(self):
        self.state = MissionState.IDLE  # mission_controller.initial_state

    def can_transition(self, target: MissionState) -> bool:
        return target in TRANSITIONS[self.state]

    def transition(self, target: MissionState) -> bool:
        """Move to `target` if allowed. Returns whether it happened - never raises."""
        if not self.can_transition(target):
            return False
        self.state = target
        return True
