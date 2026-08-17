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


class FireSmokeDetector:
    """Loads a YOLOv8n model and returns detection_event dicts for fire/smoke."""

    def __init__(self, config: Optional[ModelConfig] = None,
                 confidence_threshold: Optional[float] = None):
        self.config = config or load_model_config()
        # Defaults to config/Green_Guardians_settings.yaml's ai.confidence_threshold
        # (permissive on purpose: Person 3 owns the 0.60 candidate-trigger
        # decision in shared_policy.candidate_trigger - this module just
        # reports what it sees above its own noise floor). Callers may still
        # override per-instance, e.g. for tests or tooling scripts.
        self.confidence_threshold = (
            confidence_threshold if confidence_threshold is not None
            else self.config.confidence_threshold
        )
        self._model = YOLO(str(self.config.model_path))

    def detect(self, frame: np.ndarray, frame_id: str, timestamp: str,
               source: str = "patrol", save_evidence: bool = False) -> List[dict]:
        """Run inference on one frame and return a list of detection_event dicts."""
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

        detections = self._extract_detections(results, frame_id, timestamp, source, width, height)

        if save_evidence and detections:
            evidence_path = save_evidence_image(annotate_frame(frame, detections), frame_id)
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
