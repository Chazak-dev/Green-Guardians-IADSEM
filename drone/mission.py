"""Runs a patrol mission: takeoff, visit each waypoint capturing an image, then land."""
import os

from .drone_controller import DroneController

DEFAULT_WAYPOINTS = [
    (-3, 0, 1.5),
    (-3, 3, 1.5),
    (0, 3, 1.5),
]
# NOTE: the drone starts facing -X (~180 degrees). A first waypoint straight
# ahead of -X, like (3, 0, ...), makes the heading controller target an
# almost-exact 180 degree turn - a singularity where it can't commit to a
# turn direction and never converges. Route the first leg roughly along the
# starting heading to avoid it.


class PatrolMission:
    """Flies a drone through a list of (x, y, z) waypoints, capturing a frame at each one."""

    def __init__(self, drone=None, waypoints=None, capture_dir="results/images"):
        self.drone = drone or DroneController()
        self.waypoints = waypoints or DEFAULT_WAYPOINTS
        self.capture_dir = capture_dir

    def run(self):
        """Fly the full patrol. Returns one capture record per waypoint."""
        os.makedirs(self.capture_dir, exist_ok=True)
        captures = []

        self.drone.connect()
        self.drone.arm()
        self.drone.takeoff(altitude=self.waypoints[0][2])

        for index, (x, y, z) in enumerate(self.waypoints):
            position = self.drone.move_to(x, y, z)
            frame = self.drone.camera.capture_frame()
            image_path = os.path.join(self.capture_dir, f"waypoint_{index}.jpg")
            self.drone.camera.save_image(image_path, frame)

            captures.append({
                "waypoint_index": index,
                "target": (x, y, z),
                "position": position,
                "frame": frame,
                "image_path": image_path,
            })
            print(f"Waypoint {index}: target={(x, y, z)} reached={position} -> {image_path}")
            # later: detections = ai.detect(frame)

        self.drone.land()
        self.drone.disconnect()
        return captures


if __name__ == "__main__":
    PatrolMission().run()
