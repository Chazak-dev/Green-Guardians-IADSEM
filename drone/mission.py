"""Runs a patrol mission: takeoff, visit each waypoint capturing an image, then land."""
import os

from .drone_controller import DroneController

# Forest monitoring patrol. Coordinates match the pine ring and fire target
# in drone/webots_world/green_guardians_patrol.wbt: 5 trees form a ring of
# radius 6.5m around a clearing centered at (-12, -5), with the fire in that
# clearing at (-13.5, -5.7). See that file's comment for the tree layout.
#
# Altitude: the Pine PROTO's mesh actually reaches ~9.1m tall (checked the
# raw geometry, not assumed), so the whole route flies at one constant
# CRUISE_ALTITUDE - 3m clear of the tallest tree - for the entire patrol.
# The only descent in the whole mission is land() at the very end; there is
# no per-waypoint dip (an earlier version dropped down just for fire_
# observation and climbed back out, which looked like two separate flights
# rather than one patrol - this route deliberately avoids that). Because of
# that constant altitude, tree collision is not a concern here (12m clears
# every tree by 3m+), so waypoints aren't constrained to a collision-free
# zone the way an earlier low-altitude version needed to be.
#
# fire_observation is positioned ~10.5m from the fire rather than
# hovering over it: the camera has a fixed ~40 degree downward pitch, so at
# 12m altitude the fire only falls inside the frame from roughly 7-30m
# away (tested empirically - directly overhead put it out of frame entirely).
# ~10.5m puts it clearly in frame without being tiny.
#
# Heading safety: each leg was checked against the drone's fixed starting
# heading (~-170 to -180 degrees) and against the previous leg's bearing to
# avoid the ~180 degree turn the heading controller can't reliably converge
# on (see DroneController._heading_disturbance). The one deliberately sharp
# turn is patrol_west -> patrol_south (~135 degrees), the same magnitude
# already proven to converge in testing.
CRUISE_ALTITUDE = 12.0

PATROL_ROUTE = [
    {"name": "fire_observation", "position": (-4, -1.5, CRUISE_ALTITUDE)},  # phase 2/4: travel out, fire visible ~10.5m off
    {"name": "forest_edge", "position": (-9, -3.5, CRUISE_ALTITUDE)},       # phase 3: entering the monitoring zone
    {"name": "patrol_west", "position": (-15.9, -7.0, CRUISE_ALTITUDE)},    # phase 3: patrol, past the fire
    {"name": "patrol_south", "position": (-11, -8.5, CRUISE_ALTITUDE)},     # phase 3: patrol, south side of the clearing
    {"name": "exit_forest", "position": (-7, -4, CRUISE_ALTITUDE)},         # phase 5: leaving the forest
    {"name": "return_base", "position": (-1, -0.5, CRUISE_ALTITUDE)},       # phase 5: back near base, still at cruise altitude
]

# Longer than move_to()'s own default: these legs cover more distance/turn
# than the short in-place moves that default was originally sized for.
WAYPOINT_MAX_STEPS = 20000


class PatrolMission:
    """Flies a drone through a list of named waypoints, capturing a frame at each one."""

    def __init__(self, drone=None, waypoints=None, capture_dir="results/images"):
        self.drone = drone or DroneController()
        self.waypoints = waypoints or PATROL_ROUTE
        self.capture_dir = capture_dir

    def run(self):
        """Fly the full patrol. Returns one capture record per waypoint."""
        os.makedirs(self.capture_dir, exist_ok=True)
        captures = []

        self.drone.connect()
        self.drone.arm()
        # move_to()'s default max_steps assumed short hops; this route climbs
        # the full 12m cruise altitude in one go, at ~0.15 m/s vertical rate,
        # so takeoff/land need a much larger budget too.
        self.drone.takeoff(altitude=self.waypoints[0]["position"][2], max_steps=WAYPOINT_MAX_STEPS)

        for index, waypoint in enumerate(self.waypoints):
            name = waypoint["name"]
            x, y, z = waypoint["position"]
            position = self.drone.move_to(x, y, z, max_steps=WAYPOINT_MAX_STEPS)
            frame = self.drone.camera.capture_frame()
            image_path = os.path.join(self.capture_dir, f"{index:02d}_{name}.jpg")
            self.drone.camera.save_image(image_path, frame)

            captures.append({
                "waypoint_index": index,
                "name": name,
                "target": (x, y, z),
                "position": position,
                "frame": frame,
                "image_path": image_path,
            })
            print(f"Waypoint {index} ({name}): target={(x, y, z)} reached={position} -> {image_path}")
            # later: detections = ai.detect(frame)

        self.drone.land(max_steps=WAYPOINT_MAX_STEPS)
        self.drone.disconnect()
        return captures


if __name__ == "__main__":
    PatrolMission().run()
