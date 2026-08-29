"""Frame validation and evidence-image helpers for the AI detection module."""
from typing import List

import cv2
import numpy as np

from config.paths import EVIDENCE_DIR as _EVIDENCE_DIR
from config.paths import PROJECT_ROOT as _PROJECT_ROOT


def validate_frame(frame: np.ndarray) -> None:
    """Raise ValueError if the frame isn't a usable BGR image."""
    if frame is None or frame.size == 0:
        raise ValueError("Received an empty frame from the camera feed.")
    if frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError(f"Expected a BGR frame with 3 channels, got shape {frame.shape}.")


def annotate_frame(frame: np.ndarray, detections: List[dict]) -> np.ndarray:
    """Draw bounding boxes and labels for the given detection_event dicts."""
    annotated = frame.copy()
    for det in detections:
        x1, y1, x2, y2 = det["bbox"]
        label = f'{det["hazard"]} {det["confidence"]:.2f}'
        cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 2)
        cv2.putText(annotated, label, (x1, max(y1 - 8, 0)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    return annotated


def save_evidence_image(frame: np.ndarray, frame_id: str) -> str:
    """Save an (annotated) frame to results/images and return its project-relative path."""
    _EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = _EVIDENCE_DIR / f"{frame_id}.jpg"
    cv2.imwrite(str(path), frame)
    return str(path.relative_to(_PROJECT_ROOT)).replace("\\", "/")
