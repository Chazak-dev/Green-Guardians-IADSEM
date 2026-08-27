import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# drone/drone_controller.py does `from controller import Robot` at module
# level - Webots' own bundled package, only on sys.path when Webots is
# installed and WEBOTS_HOME is set. That single import makes `main.py`
# (which imports DroneController for its default, even though
# OrchestrationMission accepts an injected fake) fail to import at all on a
# plain dev/CI machine with no Webots, regardless of whether any test
# actually touches the real DroneController. Register a placeholder so the
# import succeeds; nothing in this test suite instantiates the real
# controller.Robot, and a genuine Webots install (which provides its own
# real "controller" module) is unaffected since this only fills in a name
# that would otherwise be missing.
if "controller" not in sys.modules:
    try:
        import controller  # noqa: F401
    except ImportError:
        fake_controller = types.ModuleType("controller")
        fake_controller.Robot = object
        sys.modules["controller"] = fake_controller
