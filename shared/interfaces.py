"""Structural interfaces backend/ can depend on instead of importing ai/ or
drone/ directly. Anything with matching methods satisfies these - the real
ai/detector.py and drone/drone_controller.py classes already do, with no
changes needed on their side.
"""
from typing import Protocol


class DetectorProtocol(Protocol):
    # Mirrors ai/detector.py's FireSmokeDetector.detect() exactly.
    def detect(self, frame, frame_id: str, timestamp: str,
               source: str = "patrol", save_evidence: bool = False) -> list[dict]:
        ...


class DroneProtocol(Protocol):
    # Mirrors drone/drone_controller.py's DroneController public methods.
    def connect(self) -> tuple:
        ...

    def arm(self) -> None:
        ...

    def takeoff(self, altitude: float, max_steps: int = ...) -> tuple:
        ...

    def move_to(self, x: float, y: float, z: float, max_steps: int = ...) -> tuple:
        ...

    def land(self, max_steps: int = ...) -> tuple:
        ...

    def disconnect(self) -> None:
        ...

    def get_position(self) -> tuple:
        ...

    def get_heading(self) -> float:
        ...

    def investigate(self, target_hint=None, max_steps: int = ...) -> tuple:
        ...
