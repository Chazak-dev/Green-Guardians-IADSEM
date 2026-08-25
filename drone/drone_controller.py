"""Connects Python to the Webots-simulated DJI Mavic 2 Pro drone.

Requires Webots to already be running with
drone/webots_world/green_guardians_patrol.wbt loaded - its Mavic2Pro node
has controller "<extern>", so it waits for this script to attach.
"""
import os
import sys

WEBOTS_HOME = os.environ.get("WEBOTS_HOME", "/Applications/Webots.app")
os.environ.setdefault("WEBOTS_HOME", WEBOTS_HOME)

_controller_python_path = os.path.join(WEBOTS_HOME, "Contents", "lib", "controller", "python")
if _controller_python_path not in sys.path:
    sys.path.insert(0, _controller_python_path)

try:
    from controller import Robot
except ImportError as exc:
    raise ImportError(
        "Could not import Webots' controller module. Make sure Webots.app is "
        f"installed and WEBOTS_HOME points to it (tried: {WEBOTS_HOME})."
    ) from exc

import math

from .camera import DroneCamera


def _clamp(value, value_min, value_max):
    return min(max(value, value_min), value_max)


class DroneController:
    """Connects to and controls the drone in the Webots simulation.

    Wraps Webots' extern-controller Robot API behind the simulator-agnostic
    interface (connect/arm/takeoff/move_to/land/disconnect) the rest of the
    project expects, so callers don't need to know anything about Webots.

    Flight stabilization (K_* constants and the per-tick motor mixing in
    _stabilize_step) reuses the tuned control law from Webots' own bundled
    Mavic 2 Pro example controller, rather than re-deriving multirotor
    control from scratch.
    """

    K_VERTICAL_THRUST = 68.5  # base motor velocity that keeps the drone level
    K_VERTICAL_OFFSET = 0.6
    K_VERTICAL_P = 3.0
    K_ROLL_P = 50.0
    K_PITCH_P = 30.0
    MAX_YAW_DISTURBANCE = 0.4
    MAX_PITCH_DISTURBANCE = -1
    TARGET_PRECISION_M = 0.5  # how close counts as "arrived", in x/y metres
    ALTITUDE_PRECISION_M = 0.3

    # investigate()'s movement-only maneuver (config: drone.investigation_maneuver).
    INVESTIGATION_APPROACH_M = 2.0  # config: investigation_approach_m
    INVESTIGATION_ANGLE_RAD = math.radians(30)  # left/right lateral offset from current heading
    INVESTIGATION_LEFT_FRAC = 0.4  # bbox-center-x / image_width below this -> "left"
    INVESTIGATION_RIGHT_FRAC = 0.6  # above this -> "right"; between -> "center"
    INVESTIGATION_HOLD_STEPS = 50  # brief settle/hold before and after the approach hop
    # Looser than TARGET_PRECISION_M (0.5m) on purpose: the maneuver is
    # explicitly a rough nudge, not precise navigation, and the standard
    # patrol-leg precision measured as needing up to ~18000 steps to satisfy
    # on a hop this short - tested live in Webots during development.
    INVESTIGATION_XY_PRECISION_M = 1.2
    INVESTIGATION_MAX_STEPS = 5000  # tuned against the loosened precision above, live in Webots

    def __init__(self):
        self._robot = None
        self._timestep = None
        self._camera = None
        self.camera = None  # public DroneCamera, set once connected
        self._imu = None
        self._gps = None
        self._gyro = None
        self._motors = None
        self._camera_pitch_motor = None
        self._connected = False
        self._armed = False

    @property
    def connected(self):
        """contracts.drone_status.connected: read-only mirror of _connected,
        so callers (main.py's orchestration loop) can report real status
        without reaching into a private attribute."""
        return self._connected

    @property
    def armed(self):
        """contracts.drone_status.armed: read-only mirror of _armed."""
        return self._armed

    def connect(self):
        """Connect to the running simulation and enable the drone's sensors."""
        self._robot = Robot()
        self._timestep = int(self._robot.getBasicTimeStep())

        self._camera = self._robot.getDevice("camera")
        self._camera.enable(self._timestep)
        self.camera = DroneCamera(self._camera)
        self._imu = self._robot.getDevice("inertial unit")
        self._imu.enable(self._timestep)
        self._gps = self._robot.getDevice("gps")
        self._gps.enable(self._timestep)
        self._gyro = self._robot.getDevice("gyro")
        self._gyro.enable(self._timestep)

        self._motors = {
            "front_left": self._robot.getDevice("front left propeller"),
            "front_right": self._robot.getDevice("front right propeller"),
            "rear_left": self._robot.getDevice("rear left propeller"),
            "rear_right": self._robot.getDevice("rear right propeller"),
        }
        for motor in self._motors.values():
            motor.setPosition(float("inf"))
            motor.setVelocity(0)

        self._camera_pitch_motor = self._robot.getDevice("camera pitch")

        self._step()  # advance one tick so sensor readings become valid
        self._connected = True
        return self.get_position()

    def get_position(self):
        """Return the drone's current (x, y, z) position in metres.

        Webots' world frame has z as altitude, positive up - unlike AirSim's
        NED convention the team's config assumed before we switched simulators.
        """
        self._require_connected()
        self._step()
        return tuple(self._gps.getValues())

    def get_heading(self):
        """Return the drone's current yaw in radians (world frame).

        Matches the atan2(dy, dx) convention _heading_disturbance uses for
        target_yaw: 0 rad faces +x, increasing (counter-clockwise) turns
        toward +y.
        """
        self._require_connected()
        self._step()
        return self._imu.getRollPitchYaw()[2]

    def disconnect(self):
        """Stop the motors and release our handle on the simulation."""
        if self._motors:
            for motor in self._motors.values():
                motor.setVelocity(0)
        self._connected = False

    def arm(self):
        """Prepare the drone for flight: tilt the camera to its patrol angle.

        Webots motors don't have a real arm/disarm signal like a flight
        controller does; this exists so takeoff()/move_to()/land() have a
        clear "ready to fly" gate, matching the interface a real drone
        would expose.
        """
        self._require_connected()
        self._camera_pitch_motor.setPosition(0.7)
        self._armed = True

    def set_camera_pitch(self, angle):
        """Adjust the camera's downward tilt in radians (arm() sets 0.7 by default)."""
        self._require_connected()
        self._camera_pitch_motor.setPosition(angle)

    def takeoff(self, altitude=1.5, max_steps=2000):
        """Climb straight up (holding x/y) until `altitude` metres is reached."""
        self._require_armed()
        x, y, _ = self.get_position()
        return self._fly_to(target_xy=(x, y), target_altitude=altitude, max_steps=max_steps)

    def move_to(self, x, y, z, max_steps=8000):
        """Fly to the given (x, y, z) position, in Webots world metres.

        Convergence time depends on how far the drone must turn to face the
        target as well as the distance - reorienting ~180 degrees can take
        several thousand simulation steps on its own, hence the generous
        default budget.
        """
        self._require_armed()
        return self._fly_to(target_xy=(x, y), target_altitude=z, max_steps=max_steps)

    def land(self, max_steps=2000):
        """Descend straight down (holding x/y) and cut the motors."""
        self._require_armed()
        x, y, _ = self.get_position()
        position = self._fly_to(target_xy=(x, y), target_altitude=0.05, max_steps=max_steps)
        for motor in self._motors.values():
            motor.setVelocity(0)
        self._armed = False
        return position

    def investigate(self, target_hint=None, max_steps=INVESTIGATION_MAX_STEPS):
        """Movement-only investigation maneuver (config: drone.investigation_maneuver).

        Pauses, holds briefly, nudges up to INVESTIGATION_APPROACH_M toward
        the rough left/center/right direction target_hint's bbox suggests
        (duck-typed: needs .bbox [x1,y1,x2,y2] and .image_width, e.g.
        shared.models.TargetHint), then holds again. Does NOT touch the
        camera or call the AI model - that's the caller's job, in its own
        loop, once this returns.

        Safety: bounded to a small lateral hop at unchanged altitude, so it
        stays at the already-obstacle-clear cruise altitude the patrol route
        was validated at, rather than requiring proximity sensing this
        project doesn't have.

        Never raises: a missing/malformed target_hint, or a directional hop
        that can't converge within max_steps, both fall back to holding
        wherever the drone already is (config's safety_fallback) instead of
        crashing the caller's investigation loop.

        Returns the (x, y, z) the drone ends up holding at.
        """
        self._require_armed()

        x, y, z = self.get_position()
        self._hold_position(x, y, z, self.INVESTIGATION_HOLD_STEPS)

        offset = self._investigation_offset(target_hint)
        if offset is not None:
            heading = self.get_heading()
            target_angle = heading + offset
            target_x = x + self.INVESTIGATION_APPROACH_M * math.cos(target_angle)
            target_y = y + self.INVESTIGATION_APPROACH_M * math.sin(target_angle)
            try:
                x, y, z = self._fly_to(
                    target_xy=(target_x, target_y), target_altitude=z, max_steps=max_steps,
                    xy_precision=self.INVESTIGATION_XY_PRECISION_M,
                )
            except RuntimeError as exc:
                print(f"Warning: investigate() could not reach approach point ({exc}); "
                      f"holding at current position instead.")
                x, y, z = self.get_position()

        self._hold_position(x, y, z, self.INVESTIGATION_HOLD_STEPS)
        return (x, y, z)

    def _fly_to(self, target_xy, target_altitude, max_steps,
                xy_precision=None, altitude_precision=None):
        """Run the stabilization loop until the drone reaches target_xy/target_altitude.

        xy_precision/altitude_precision default to TARGET_PRECISION_M/
        ALTITUDE_PRECISION_M (patrol-leg precision). investigate() passes a
        looser xy_precision for its short 2m hop - the controller here is
        tuned for multi-metre patrol legs, and empirically takes far longer
        than is reasonable to settle within 0.5m on a target only 2m away
        (observed needing up to ~18000 steps in testing, plausibly blowing
        the backend's 15s investigation timeout on its own) - a rough
        investigative nudge doesn't need that tight a tolerance.
        """
        xy_precision = self.TARGET_PRECISION_M if xy_precision is None else xy_precision
        altitude_precision = (
            self.ALTITUDE_PRECISION_M if altitude_precision is None else altitude_precision
        )
        target_x, target_y = target_xy
        for _ in range(max_steps):
            x, y, altitude = self._stabilize_step(target_x, target_y, target_altitude)
            close_enough_xy = math.hypot(target_x - x, target_y - y) < xy_precision
            close_enough_altitude = abs(target_altitude - altitude) < altitude_precision
            if close_enough_xy and close_enough_altitude:
                return (x, y, altitude)
        raise RuntimeError(
            f"Did not reach target ({target_x}, {target_y}, {target_altitude}) "
            f"within {max_steps} simulation steps."
        )

    def _stabilize_step(self, target_x, target_y, target_altitude):
        """Read sensors, apply one tick of the Mavic stabilization law, advance the sim."""
        roll, pitch, yaw = self._imu.getRollPitchYaw()
        x, y, altitude = self._gps.getValues()
        roll_acceleration, pitch_acceleration, _ = self._gyro.getValues()

        yaw_disturbance, pitch_disturbance = self._heading_disturbance(
            target_x, target_y, x, y, yaw
        )

        roll_input = self.K_ROLL_P * _clamp(roll, -1, 1) + roll_acceleration
        pitch_input = self.K_PITCH_P * _clamp(pitch, -1, 1) + pitch_acceleration + pitch_disturbance
        yaw_input = yaw_disturbance
        clamped_altitude_difference = _clamp(
            target_altitude - altitude + self.K_VERTICAL_OFFSET, -1, 1
        )
        vertical_input = self.K_VERTICAL_P * clamped_altitude_difference ** 3

        front_left = self.K_VERTICAL_THRUST + vertical_input - yaw_input + pitch_input - roll_input
        front_right = self.K_VERTICAL_THRUST + vertical_input + yaw_input + pitch_input + roll_input
        rear_left = self.K_VERTICAL_THRUST + vertical_input + yaw_input - pitch_input - roll_input
        rear_right = self.K_VERTICAL_THRUST + vertical_input - yaw_input - pitch_input + roll_input

        self._motors["front_left"].setVelocity(front_left)
        self._motors["front_right"].setVelocity(-front_right)
        self._motors["rear_left"].setVelocity(-rear_left)
        self._motors["rear_right"].setVelocity(rear_right)

        self._step()
        return x, y, altitude

    def _hold_position(self, x, y, z, steps):
        """Run a fixed number of stabilization ticks at (x, y, z) - a brief
        hover with no convergence check, unlike _fly_to."""
        for _ in range(steps):
            self._stabilize_step(x, y, z)

    @staticmethod
    def _investigation_offset(target_hint):
        """Bucket a TargetHint-shaped bbox center into a left/center/right
        lateral angle offset (radians) from the drone's current heading.

        Returns None only when target_hint is missing/malformed, signalling
        investigate() to skip directional movement entirely (safety_fallback:
        hover in place). A center hint returns 0.0 (still moves, straight
        ahead) - callers with no hint at all should pass target_hint=None.
        """
        if not target_hint or not getattr(target_hint, "bbox", None) \
                or not getattr(target_hint, "image_width", None):
            return None
        x1, _, x2, _ = target_hint.bbox
        frac = ((x1 + x2) / 2) / target_hint.image_width
        if frac < DroneController.INVESTIGATION_LEFT_FRAC:
            return DroneController.INVESTIGATION_ANGLE_RAD
        if frac > DroneController.INVESTIGATION_RIGHT_FRAC:
            return -DroneController.INVESTIGATION_ANGLE_RAD
        return 0.0

    @staticmethod
    def _heading_disturbance(target_x, target_y, x, y, yaw):
        """Yaw/pitch nudges (Webots Mavic example's approach) to steer toward the target."""
        target_yaw = math.atan2(target_y - y, target_x - x)
        angle_left = (target_yaw - yaw + 2 * math.pi) % (2 * math.pi)
        if angle_left > math.pi:
            angle_left -= 2 * math.pi

        yaw_disturbance = DroneController.MAX_YAW_DISTURBANCE * angle_left / (2 * math.pi)
        pitch_disturbance = _clamp(
            math.log10(abs(angle_left)) if angle_left != 0 else DroneController.MAX_PITCH_DISTURBANCE,
            DroneController.MAX_PITCH_DISTURBANCE,
            0.1,
        )
        return yaw_disturbance, pitch_disturbance

    def _step(self):
        if self._robot.step(self._timestep) == -1:
            raise RuntimeError("Webots simulation ended or was closed.")

    def _require_connected(self):
        if not self._connected:
            raise RuntimeError("Not connected. Call connect() first.")

    def _require_armed(self):
        self._require_connected()
        if not self._armed:
            raise RuntimeError("Not armed. Call arm() first.")


if __name__ == "__main__":
    drone = DroneController()

    position = drone.connect()
    print(f"Connected. Starting position: {position}")

    drone.arm()
    print("Armed.")

    position = drone.takeoff(altitude=1.5)
    print(f"Took off. Position: {position}")

    position = drone.move_to(3, 3, 1.5)
    print(f"Reached waypoint. Position: {position}")

    frame = drone.camera.capture_frame()
    print(f"Captured frame: shape={frame.shape}, dtype={frame.dtype}")
    saved_path = drone.camera.save_image("results/images/patrol_capture.jpg", frame)
    print(f"Saved capture to: {saved_path}")

    position = drone.land()
    print(f"Landed. Position: {position}")

    drone.disconnect()
    print("Disconnected.")
