"""Fire/smoke detection pipeline: YOLOv8n inference over drone camera frames.

Produces detection_event records matching the contract frozen in
config/Green_Guardians_settings.yaml, so the Mission Controller (Person 3)
can consume them without translation.
"""
import uuid
from typing import List, Optional

import numpy as np
from ultralytics import YOLO

from ai.image_processing import annotate_frame, save_evidence_image, validate_frame
from ai.model_config import ModelConfig, load_model_config
from shared.models import CameraFrameMetadata

# Permissive on purpose: Person 3 owns the 0.60 candidate-trigger decision
# (shared_policy.candidate_trigger). This module reports what it sees.
DEFAULT_CONFIDENCE_THRESHOLD = 0.25


class FireSmokeDetector:
    """Loads a YOLOv8n model and returns detection_event dicts for fire/smoke."""

    def __init__(self, config: Optional[ModelConfig] = None,
                 confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD):
        self.config = config or load_model_config()
        self.confidence_threshold = confidence_threshold
        self._model = YOLO(str(self.config.model_path))

    def detect(self, frame: np.ndarray, frame_metadata: CameraFrameMetadata,
               source: str = "patrol", save_evidence: bool = False) -> List[dict]:
        """Run inference on one frame and return a list of detection_event dicts.

        frame_metadata is shared.models.CameraFrameMetadata, the bundle
        Person 2's camera feed is expected to produce (contracts.
        camera_frame_metadata). Width/height are still read from the actual
        array, not frame_metadata, so a stale caller value can't silently
        disagree with the real frame; drone_position is accepted but
        unused here since detection_event doesn't carry it.
        """
        validate_frame(frame)
        height, width = frame.shape[:2]

        results = self._model.predict(
            frame,
            imgsz=self.config.imgsz,
            iou=self.config.iou_threshold,
            conf=self.confidence_threshold,
            device=self.config.device,
            verbose=False,
        )[0]

        detections = self._extract_detections(
            results, frame_metadata.frame_id, frame_metadata.timestamp, source, width, height
        )

        if save_evidence and detections:
            evidence_path = save_evidence_image(annotate_frame(frame, detections), frame_metadata.frame_id)
            for det in detections:
                det["image_path"] = evidence_path

        return detections

    def _extract_detections(self, results, frame_id: str, timestamp: str, source: str,
                             width: int, height: int) -> List[dict]:
        detections = []
        names = results.names
        for box in results.boxes:
            class_name = names[int(box.cls)].lower()
            if class_name not in self.config.classes:
                continue
            x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
            detections.append({
                "detection_id": f"det-{uuid.uuid4().hex[:8]}",
                "frame_id": frame_id,
                "timestamp": timestamp,
                "hazard": class_name,
                "confidence": round(float(box.conf), 4),
                "bbox": [x1, y1, x2, y2],
                "image_width": width,
                "image_height": height,
                "image_path": None,
                "source": source,
            })
        return detections
