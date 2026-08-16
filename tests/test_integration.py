import cv2

from ai.detector import FireSmokeDetector
from shared.models import CameraFrameMetadata, Position

SAMPLE_IMAGE = "sample_data/images/fire.jpg"


def test_detect_runs_end_to_end_on_sample_image():
    """Exercises the full pipeline (real model load + inference) so the
    plumbing is proven before fine-tuned fire/smoke weights exist."""
    frame = cv2.imread(SAMPLE_IMAGE)
    assert frame is not None, f"expected {SAMPLE_IMAGE} to exist"

    frame_metadata = CameraFrameMetadata(
        frame_id="frame-smoke-test", timestamp="2026-08-11T00:00:00Z",
        image_width=frame.shape[1], image_height=frame.shape[0],
        drone_position=Position(x=0.0, y=0.0, z=0.0),
    )
    detector = FireSmokeDetector()
    detections = detector.detect(frame, frame_metadata, source="patrol")

    assert isinstance(detections, list)
    for det in detections:
        assert det["hazard"] in {"fire", "smoke"}
