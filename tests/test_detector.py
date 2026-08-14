import numpy as np
import pytest

from ai.detector import FireSmokeDetector
from ai.model_config import ModelConfig


class _FakeBox:
    def __init__(self, cls_id, conf, xyxy):
        self.cls = cls_id
        self.conf = conf
        self.xyxy = [np.array(xyxy, dtype=float)]


class _FakeResults:
    def __init__(self, names, boxes):
        self.names = names
        self.boxes = boxes


@pytest.fixture
def detector():
    """A detector with its config set directly, skipping YOLO weight loading
    so this test doesn't depend on any model file being present."""
    instance = FireSmokeDetector.__new__(FireSmokeDetector)
    instance.config = ModelConfig(
        model_path=None,
        classes=["fire", "smoke"],
        imgsz=640,
        iou_threshold=0.45,
        device=None,
        inference_fps_target=2,
    )
    instance.confidence_threshold = 0.25
    return instance


def test_extract_detections_matches_detection_event_contract(detector):
    results = _FakeResults(
        names={0: "fire", 1: "person"},
        boxes=[
            _FakeBox(0, 0.91, [120, 80, 300, 250]),
            _FakeBox(1, 0.99, [10, 10, 50, 50]),  # not fire/smoke, must be dropped
        ],
    )

    detections = detector._extract_detections(
        results, frame_id="frame-0042", timestamp="2026-08-11T00:00:00Z",
        source="patrol", width=640, height=480,
    )

    assert len(detections) == 1
    det = detections[0]
    assert set(det.keys()) == {
        "detection_id", "frame_id", "timestamp", "hazard", "confidence",
        "bbox", "image_width", "image_height", "image_path", "source",
    }
    assert det["hazard"] == "fire"
    assert det["confidence"] == 0.91
    assert det["bbox"] == [120, 80, 300, 250]
    assert det["frame_id"] == "frame-0042"
    assert det["source"] == "patrol"
    assert det["image_width"] == 640
    assert det["image_height"] == 480
    assert det["image_path"] is None


def test_extract_detections_returns_empty_list_when_nothing_matches(detector):
    results = _FakeResults(names={0: "person"}, boxes=[_FakeBox(0, 0.99, [0, 0, 10, 10])])

    detections = detector._extract_detections(
        results, frame_id="frame-1", timestamp="2026-08-11T00:00:00Z",
        source="investigation", width=640, height=480,
    )

    assert detections == []
