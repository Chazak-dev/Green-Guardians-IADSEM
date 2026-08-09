"""Captures frames from the drone's camera and converts them to OpenCV/NumPy format."""
import cv2
import numpy as np


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

    def save_image(self, path, frame=None):
        """Save a frame to disk. Captures a fresh frame if none is given."""
        if frame is None:
            frame = self.capture_frame()
        cv2.imwrite(path, frame)
        return path
