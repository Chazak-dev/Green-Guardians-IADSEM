"""Application entry point. Wiring only — detection logic lives in ai/."""
import json
from datetime import datetime, timezone
from pathlib import Path

import cv2

from ai.detector import FireSmokeDetector

SAMPLE_IMAGE = Path(__file__).resolve().parent / "sample_data" / "images" / "fire.jpg"


def main() -> None:
    frame = cv2.imread(str(SAMPLE_IMAGE))
    if frame is None:
        raise FileNotFoundError(f"Could not read sample image: {SAMPLE_IMAGE}")

    detector = FireSmokeDetector()
    detections = detector.detect(
        frame,
        frame_id="frame-main-demo",
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        source="patrol",
    )

    print(json.dumps(detections, indent=2))


if __name__ == "__main__":
    main()
