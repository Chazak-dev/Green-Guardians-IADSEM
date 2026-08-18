"""Captures frames from the drone's camera and converts them to OpenCV/NumPy format."""
import uuid
from datetime import datetime, timezone

import cv2
import numpy as np

from shared.models import CameraFrameMetadata, Position


class DroneCamera:
    """Wraps a Webots Camera device, converting frames to OpenCV-ready BGR NumPy arrays."""

    def __init__(self, webots_camera):
        self._camera = webots_camera

    def capture_frame(self):
        """Return the current camera frame as a BGR NumPy array (OpenCV format)."""
        width = self._camera.getWidth()
        height = self._camera.getHeight()
        raw = self._camera.getImage()
        image = np.frombuffer(raw, np.uint8).reshape((height, width, 4))
        return image[:, :, :3].copy()  # Webots gives BGRA; drop alpha for BGR

    def capture_image(self):
        """Alias for capture_frame(), matching the project's requested interface."""
        return self.capture_frame()

    def capture_frame_metadata(self, drone_position):
        """Capture a frame and its CameraFrameMetadata (shared/models.py contract).

        drone_position is the (x, y, z) tuple from DroneController.get_position() -
        this class has no drone reference of its own, so the caller (mission.py,
        which already talks to both) supplies it. Returns (frame, metadata).
        """
        frame = self.capture_frame()
        height, width = frame.shape[:2]
        metadata = CameraFrameMetadata(
            frame_id=f"frame-{uuid.uuid4().hex[:8]}",
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            image_width=width,
            image_height=height,
            drone_position=Position(*drone_position),
        )
        return frame, metadata

    def save_image(self, path, frame=None):
        """Save a frame to disk. Captures a fresh frame if none is given."""
        if frame is None:
            frame = self.capture_frame()
        cv2.imwrite(path, frame)
        return path
