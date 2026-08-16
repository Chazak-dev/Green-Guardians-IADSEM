"""Application entry point. Wiring only — detection logic lives in ai/."""
import json
from datetime import datetime, timezone
from pathlib import Path

import cv2

from ai.detector import FireSmokeDetector
from shared.models import CameraFrameMetadata, Position

SAMPLE_IMAGE = Path(__file__).resolve().parent / "sample_data" / "images" / "fire.jpg"


def main() -> None:
    frame = cv2.imread(str(SAMPLE_IMAGE))
    if frame is None:
        raise FileNotFoundError(f"Could not read sample image: {SAMPLE_IMAGE}")

    frame_metadata = CameraFrameMetadata(
        frame_id="frame-main-demo",
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        image_width=frame.shape[1],
        image_height=frame.shape[0],
        drone_position=Position(x=0.0, y=0.0, z=0.0),  # no real drone for this static-image demo
    )

    detector = FireSmokeDetector()
    detections = detector.detect(frame, frame_metadata, source="patrol")

    print(json.dumps(detections, indent=2))


if __name__ == "__main__":
    main()
