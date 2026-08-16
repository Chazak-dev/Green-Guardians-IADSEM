"""Round 2 of the training-dataset collection tour: a longer, better-isolated
loop than dataset_collection.py's round 1, covering the full hazard variety
requested for round 2 (very large fire, medium, small, smoke-only, smoke from
a tree, fire+smoke together, fire at a house, fire at a car, and a dedicated
false-positive/negative zone).

Round 1 (dataset_collection.py) put every scenario within a ~15m cluster near
base, which let neighboring hazards bleed into each other's frames and forced
per-leg category labels that weren't always true for the whole leg (measured
hit rates as low as 13-19% on the weakest categories). Round 2 fixes both:

  - 9 hazard zones spaced >=25m apart from each other AND >=25-30m from every
    round-1 object, so no two hazards - old or new - can ever share a frame
    (see drone/webots_world/green_guardians_patrol.wbt's round-2 zone
    comment for the exact placements and margins).
  - Frames are labelled by measuring the drone's actual distance to every
    hazard's real world position at capture time, not by which leg is
    currently flying. A frame only gets a hazard's category if the drone is
    within VISIBLE_RADIUS of it; otherwise it's "negative". This is strictly
    more honest than round 1's fixed per-leg label.

The route was solved computationally (not hand-tuned) for three constraints
at once: every turn stays >=90 degrees clear of the ~180 degree heading
singularity (see DroneController._heading_disturbance), every zone pair is
>=25m apart, and no leg's straight-line path clips the round-1 cluster's
bounding box. See PLAN.md-equivalent notes below for the actual numbers.
"""
import csv
import math
import os

from .drone_controller import DroneController

# (category, label, x, y) - flight waypoints. Each hazard's real geometry
# sits exactly at its flight waypoint (see HAZARD_POSITIONS) - matching
# round 1's proven design, not something re-derived from scratch. Two earlier
# variants of this route (hazard offset sideways from the path, then offset
# along the approach bearing beyond the waypoint) both came back with mostly
# blank frames when test-flown; a diagnostic run logging distance-to-hazard
# against saved frames (see scratchpad/framing_diagnostic.py during
# development) showed the low pass's fire only becomes visible within
# roughly 10-12m, near the top of frame, not the far offset distances either
# variant assumed. Putting the hazard directly at the waypoint and relying on
# continuous capture *during the approach* - exactly how dataset_collection.py's
# round 1 worked - sidesteps needing to predict that window precisely.
# Heading safety: computed for this exact sequence starting from the drone's
# fixed spawn heading (~-180 degrees) - max turn is 88 degrees (base->Z1),
# every other turn is <=42 degrees. See the module docstring.
FLIGHT_ROUTE = [
    ("fire_medium", "zone1", -1, -29),
    ("fire_large", "zone2", -10, -55),
    ("fire_small", "zone3", -1, -81),
    ("smoke_only", "zone4", 23, -94),
    ("smoke_tree", "zone5", 50, -90),
    ("fire_smoke", "zone6", 68, -69),
    ("fire_house", "zone7", 68, -41),
    ("fire_car", "zone8", 50, -20),
    ("negative", "zone9", 23, -16),
]

# Real (x, y) of each hazard's geometry in the .wbt file (the actual fire/
# smoke/car/house position, not the flight waypoint) - used to label frames
# by measured distance rather than by which leg is currently flying.
HAZARD_POSITIONS = {
    "fire_medium": (-1, -29),
    "fire_large": (-10, -55),
    "fire_small": (-1, -81),
    "smoke_only": (23, -94),
    "smoke_tree": (50, -90),
    "fire_smoke": (68, -69),
    "fire_house": (68, -41),
    "fire_car": (50, -20),
    "negative": (23, -16),
}

# A frame is labelled with a hazard's category only if the drone is within
# this distance of it at capture time. The framing_diagnostic.py probe
# (logged distance-to-hazard alongside each saved frame while approaching
# zone1) showed the low pass's fire stops being visible somewhere around
# 12-14m out, near the top edge of frame - this stays close to that measured
# cutoff rather than the wider 18m guess an earlier version used, which
# mislabelled a lot of empty-frame "approach" shots as positives.
VISIBLE_RADIUS_M = 13.0

# (pass label, altitude metres, camera downward pitch radians). The two
# outer values (high, low) are round 1's exact proven combination (dataset_
# collection.py's PASSES) - the two in between interpolate for extra
# altitude/angle variety without straying into untested territory.
PASSES = [
    ("high", 25.0, 0.4),
    ("mid_high", 17.0, 0.6),
    ("mid_low", 13.5, 0.8),
    ("low", 10.5, 1.0),
]

CAPTURE_EVERY_N_STEPS = 130
LEG_MAX_STEPS = 30000

# Guaranteed captures at these distances-to-target, in addition to the
# periodic interval above. A second diagnostic run (framing_diagnostic2.py,
# logging distance-to-target directly instead of distance-to-hazard) showed
# the low pass's fire is well-centered in frame from roughly 8m down to 3m
# out, and basically gone by ~1-2m (about to pass underneath) or beyond ~12m
# (not yet in frame). Relying on CAPTURE_EVERY_N_STEPS alone mostly missed
# that window - it's a few hundred steps wide against a leg that can run
# several thousand, so most periodic captures landed either too early or
# too late. These thresholds span a wider band than just the low pass's
# window since the steeper/shallower passes' windows shift with altitude
# and pitch, and hitting each one explicitly - once per leg - beats hoping
# the fixed step interval lines up.
DISTANCE_CAPTURE_THRESHOLDS_M = [14, 11, 9, 7, 5, 3]


class DatasetCollectionRound2Mission:
    """Flies FLIGHT_ROUTE once per entry in PASSES, saving frames along the way."""

    def __init__(self, drone=None, capture_dir="results/images/dataset_round2"):
        self.drone = drone or DroneController()
        self.capture_dir = capture_dir
        self._counts = {}
        # (path, category, distance_to_that_category's_hazard) for every
        # saved frame - lets a filtering pass keep/drop by measured distance
        # (ground truth) instead of guessing from pixel colors. A same-session
        # attempt at HSV color filtering fell apart on contact with real
        # frames: an orange roof tile read as "fire" and plain sand read as
        # "smoke", so a clean negative frame with a house in the background
        # scored *worse* than an actual smoke frame. Distance to the hazard's
        # real (x, y) in the world doesn't have that problem.
        self._metadata = []

    def run(self):
        os.makedirs(self.capture_dir, exist_ok=True)

        self.drone.connect()
        self.drone.arm()
        self.drone.takeoff(altitude=PASSES[0][1], max_steps=LEG_MAX_STEPS)

        for pass_label, altitude, camera_pitch in PASSES:
            self.drone.set_camera_pitch(camera_pitch)
            print(f"--- {pass_label} pass: altitude={altitude}m, camera_pitch={camera_pitch} ---")
            for category, label, x, y in FLIGHT_ROUTE:
                self._fly_leg_and_capture(f"{pass_label}_{label}", x, y, altitude)

        # Every frame is already on disk by this point - write metadata before
        # attempting to land, so a landing failure can never cost the run's
        # data. land() has twice needed more than a very generous budget to
        # settle after a long multi-pass flight (residual horizontal drift
        # from the last leg slows the vertical convergence law's approach
        # to 0), so its failure is treated as non-fatal cleanup, not a run
        # failure - all the real work (flying the route, capturing frames)
        # is already done and safely saved by this line.
        self._write_metadata()
        try:
            self.drone.land(max_steps=LEG_MAX_STEPS * 2)
        except RuntimeError as exc:
            print(f"Warning: land() did not settle ({exc}); data is already saved, continuing.")
        self.drone.disconnect()
        print("Frames captured per category:", self._counts)
        return dict(self._counts)

    def _write_metadata(self):
        metadata_path = os.path.join(self.capture_dir, "metadata.csv")
        with open(metadata_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["filename", "category", "distance_to_hazard_m"])
            writer.writerows(self._metadata)

    def _fly_leg_and_capture(self, label, target_x, target_y, altitude):
        """Fly one leg toward (target_x, target_y, altitude), saving labelled frames along the way."""
        drone = self.drone
        step_count = 0
        remaining_thresholds = list(DISTANCE_CAPTURE_THRESHOLDS_M)
        for _ in range(LEG_MAX_STEPS):
            x, y, current_altitude = drone._stabilize_step(target_x, target_y, altitude)
            step_count += 1
            dist_to_target = ((target_x - x) ** 2 + (target_y - y) ** 2) ** 0.5

            if step_count % CAPTURE_EVERY_N_STEPS == 0:
                self._save_frame(x, y)

            while remaining_thresholds and dist_to_target < remaining_thresholds[0]:
                remaining_thresholds.pop(0)
                self._save_frame(x, y)

            close_enough_xy = dist_to_target < drone.TARGET_PRECISION_M
            close_enough_altitude = abs(altitude - current_altitude) < drone.ALTITUDE_PRECISION_M
            if close_enough_xy and close_enough_altitude:
                self._save_frame(x, y)  # one frame right at arrival too
                print(f"{label}: reached ({x:.2f}, {y:.2f}, {current_altitude:.2f})")
                return

        raise RuntimeError(f"{label}: did not reach ({target_x}, {target_y}, {altitude}) in time.")

    def _category_for_position(self, x, y):
        """Label a frame by measured distance to every hazard, not by which leg is flying.

        Returns (category, distance_to_that_hazard) - distance is 0.0 for
        "negative" (no single hazard it's measured against).
        """
        nearest_category = "negative"
        nearest_distance = VISIBLE_RADIUS_M
        for category, (hx, hy) in HAZARD_POSITIONS.items():
            d = math.hypot(hx - x, hy - y)
            if d < nearest_distance:
                nearest_distance = d
                nearest_category = category
        return nearest_category, (nearest_distance if nearest_category != "negative" else 0.0)

    def _save_frame(self, x, y):
        category, distance = self._category_for_position(x, y)
        index = self._counts.get(category, 0) + 1
        self._counts[category] = index
        filename = f"{category}_{index:04d}.jpg"
        path = os.path.join(self.capture_dir, filename)
        self.drone.camera.save_image(path)
        self._metadata.append((filename, category, round(distance, 2)))


if __name__ == "__main__":
    DatasetCollectionRound2Mission().run()
