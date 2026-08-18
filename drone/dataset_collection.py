"""Flies a long multi-altitude tour past every fire/smoke/negative scenario in
the world, saving a frame every few seconds throughout - for Person 2's YOLO
training set (see the AI team's dataset checklist: multiple distances/angles/
altitudes per category, plus negatives, without near-duplicate consecutive
frames).

Captures continuously during each leg rather than only on arrival: a burst of
frames from varying angles as the drone approaches/passes a site is both more
robust than needing one perfectly-centered shot, and closer to what a real
training dataset needs anyway (see drone/mission.py's heading-safety notes for
why hitting one exact "look-at" waypoint isn't always reliable).

The same site tour runs three times, at three altitudes with three camera
angles, to cover the checklist's altitude/angle variation:
  high   (25m, shallow pitch)  - wide-area overview
  medium (12m, normal pitch)   - the operational patrol altitude (see mission.py)
  low    (10.5m, steep pitch)  - close-in detail, just above the ~9.1m tree
                                  canopy (checked the raw Pine mesh, not
                                  assumed - going lower risks clipping a tree)
"""
import os

from .drone_controller import DroneController

# (category, label, x, y) - the tour's stops, reused across every altitude
# pass. category becomes the output filename prefix (matches the checklist's
# naming convention, e.g. fire_small_0001.jpg). Ordered to build heading up
# gradually leg by leg (see drone/mission.py) rather than jumping to an
# awkward bearing in one hop. far_south/far_return swing toward the world's
# original, more distant Pine trees for extra distance and background
# variety beyond the near forest cluster the fire/smoke sites sit in.
SITE_WAYPOINTS = [
    ("negative", "forest_edge", -9, -3.5),
    ("fire_medium", "close_pass", -11.3, -4.6),
    ("fire_medium", "north_pass", -14.6, -3.5),          # 2nd angle - was the weakest baseline category
    ("negative", "deep_forest", -15.9, -7.0),
    ("fire_large", "approach", -20, -4),
    ("fire_large", "close_pass", -22, -2),
    ("fire_large", "southwest_pass", -24, -4),            # 2nd angle - lowest hit rate in testing (13%)
    ("negative", "false_positive_glare", -18, -4),
    ("fire_multi", "approach", -18, -9),
    ("fire_multi", "cluster_pass", -20.5, -10.5),
    ("fire_small", "approach", -16, -10.5),
    ("fire_small", "close_pass", -13.8, -11.6),
    ("fire_small", "south_pass", -15, -13),               # 2nd angle - second-lowest hit rate (19%)
    ("negative", "false_positive_rock", -9, -15),
    ("negative", "south_forest", -11, -8.5),
    ("smoke_only", "approach", -13, -14),
    ("smoke_only", "close_pass", -13, -16),
    ("negative", "far_south", -15, -22),
    ("negative", "far_return", -11, -17),
    ("negative", "exit_forest", -7, -4),
    ("negative", "return_base", -1, -0.5),
]

# (pass label, altitude metres, camera downward pitch radians).
PASSES = [
    ("high", 25.0, 0.4),
    ("medium", 12.0, 0.7),
    ("low", 10.5, 1.0),
]

# ~2.4s of simulated time between frames (basicTimeStep=8ms) - at the
# controller's ~0.17-0.2 m/s cruise speed that's roughly half a metre of
# travel per frame, enough to avoid near-duplicate consecutive shots.
CAPTURE_EVERY_N_STEPS = 300

# Generous budget: a pass-to-pass altitude change (up to ~14.5m, high->medium)
# takes longer to converge than a same-altitude horizontal hop.
LEG_MAX_STEPS = 25000


class DatasetCollectionMission:
    """Flies SITE_WAYPOINTS once per entry in PASSES, saving frames along the way."""

    def __init__(self, drone=None, capture_dir="results/images/dataset"):
        self.drone = drone or DroneController()
        self.capture_dir = capture_dir
        self._counts = {}

    def run(self):
        """Fly the full multi-pass tour. Returns frames saved per category."""
        os.makedirs(self.capture_dir, exist_ok=True)

        self.drone.connect()
        self.drone.arm()
        self.drone.takeoff(altitude=PASSES[0][1], max_steps=LEG_MAX_STEPS)

        for pass_label, altitude, camera_pitch in PASSES:
            self.drone.set_camera_pitch(camera_pitch)
            print(f"--- {pass_label} pass: altitude={altitude}m, camera_pitch={camera_pitch} ---")
            for category, label, x, y in SITE_WAYPOINTS:
                self._fly_leg_and_capture(category, f"{pass_label}_{label}", x, y, altitude)

        self.drone.land(max_steps=LEG_MAX_STEPS)
        self.drone.disconnect()
        print("Frames captured per category:", self._counts)
        return dict(self._counts)

    def _fly_leg_and_capture(self, category, label, target_x, target_y, altitude):
        """Fly one leg toward (target_x, target_y, altitude), saving frames along the way."""
        drone = self.drone
        step_count = 0
        for _ in range(LEG_MAX_STEPS):
            x, y, current_altitude = drone._stabilize_step(target_x, target_y, altitude)
            step_count += 1

            if step_count % CAPTURE_EVERY_N_STEPS == 0:
                self._save_frame(category)

            close_enough_xy = ((target_x - x) ** 2 + (target_y - y) ** 2) ** 0.5 < drone.TARGET_PRECISION_M
            close_enough_altitude = abs(altitude - current_altitude) < drone.ALTITUDE_PRECISION_M
            if close_enough_xy and close_enough_altitude:
                self._save_frame(category)  # one frame right at arrival too
                print(f"{category}/{label}: reached ({x:.2f}, {y:.2f}, {current_altitude:.2f})")
                return

        raise RuntimeError(f"{category}/{label}: did not reach ({target_x}, {target_y}, {altitude}) in time.")

    def _save_frame(self, category):
        index = self._counts.get(category, 0) + 1
        self._counts[category] = index
        path = os.path.join(self.capture_dir, f"{category}_{index:04d}.jpg")
        self.drone.camera.save_image(path)


if __name__ == "__main__":
    DatasetCollectionMission().run()
