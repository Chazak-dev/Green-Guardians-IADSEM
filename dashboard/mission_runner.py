"""Launches a full, live Green Guardians mission: starts Webots (visible, so
the drone's actual patrol path can be watched) against
drone/webots_world/green_guardians_patrol.wbt running (not paused), then runs
main.py as its extern controller.

Pure subprocess orchestration - deliberately does not import main.py or any
other project package, so it has no exposure to the sys.path quirk
config/paths.py documents (streamlit run dashboard/app.py puts dashboard/,
not the repo root, on sys.path). Paths are computed the same way
dashboard/app.py already computes its own.

start_mission_async() is what the dashboard button uses: it launches the
mission on a background thread and returns immediately, so the caller can
keep polling results/mission_log.jsonl (backend/logger.py appends to it in
real time as the mission runs) instead of blocking until the whole mission
- every waypoint, every investigation - is done. run_full_mission() is the
blocking version underneath it, also usable directly from a terminal:
    python dashboard/mission_runner.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEBOTS_HOME = os.environ.get("WEBOTS_HOME", "/Applications/Webots.app")
WEBOTS_BIN = Path(WEBOTS_HOME) / "Contents" / "MacOS" / "webots"
WORLD_PATH = PROJECT_ROOT / "drone" / "webots_world" / "green_guardians_patrol.wbt"
WORLD_PATH_LONG = PROJECT_ROOT / "drone" / "webots_world" / "green_guardians_long_patrol.wbt"
MAIN_PY = PROJECT_ROOT / "main.py"

DEFAULT_TIMEOUT_SECONDS = 600
WEBOTS_TERMINATE_GRACE_SECONDS = 5


def _kill_existing_webots() -> None:
    """Best-effort: ensure a single clean Webots instance per run, so a
    leftover manually-opened session can't conflict over the extern
    controller IPC connection."""
    subprocess.run(
        ["pkill", "-f", str(WEBOTS_BIN)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def run_full_mission(timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS, long_patrol: bool = False) -> dict:
    """Runs one full mission end-to-end (takeoff -> patrol -> detect ->
    investigate -> confirm/reject -> return -> land) against a headless
    Webots instance, then shuts that instance down.

    long_patrol=True runs the longer fire+smoke test world/route
    (green_guardians_long_patrol.wbt / drone/mission.py's PATROL_ROUTE_LONG)
    instead of the default short demo one.

    Returns {"exit_code", "stdout", "stderr", "timed_out"}.
    """
    if not WEBOTS_BIN.exists():
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": f"Webots not found at {WEBOTS_BIN}. Set WEBOTS_HOME if it's installed elsewhere.",
            "timed_out": False,
        }

    _kill_existing_webots()

    world_path = WORLD_PATH_LONG if long_patrol else WORLD_PATH
    webots_proc = subprocess.Popen(
        [
            str(WEBOTS_BIN),
            "--mode=fast",
            "--batch",
            str(world_path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    timed_out = False
    env = {**os.environ, "GG_LONG_PATROL": "1"} if long_patrol else os.environ
    try:
        result = subprocess.run(
            [sys.executable, str(MAIN_PY)],
            cwd=str(PROJECT_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        exit_code = result.returncode
        stdout = result.stdout
        stderr = result.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = -1
        stdout = exc.stdout or ""
        stderr = (exc.stderr or "") + "\nmain.py timed out and was killed."
    finally:
        webots_proc.terminate()
        try:
            webots_proc.wait(timeout=WEBOTS_TERMINATE_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            webots_proc.kill()
            webots_proc.wait()

    return {
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "timed_out": timed_out,
    }


@dataclass
class MissionRun:
    """Mutable status of one async mission run, polled by the dashboard on
    every auto-refresh tick instead of blocking on the whole mission."""
    status: str = "running"  # "running" | "success" | "failed" | "timed_out"
    exit_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    started_at: float = field(default_factory=time.monotonic)
    # Wall-clock UTC, same format as backend/logger.py's LogEvent timestamps
    # (main.py's _now_iso()) - lets the dashboard filter results/mission_log.jsonl
    # down to just this run's events (e.g. the live camera feed), instead of
    # showing whatever's most recent across every mission ever run.
    started_at_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    finished_at: Optional[float] = None


def start_mission_async(timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS, long_patrol: bool = False) -> MissionRun:
    """Launches run_full_mission() on a background thread and returns
    immediately. The caller (dashboard/app.py) stores the returned MissionRun
    in st.session_state and reads its `status` on each auto-refresh - the
    thread mutates it in place as the mission progresses and finishes, so no
    blocking wait is needed to see the mission run live."""
    run = MissionRun()

    def _worker() -> None:
        outcome = run_full_mission(timeout_seconds, long_patrol=long_patrol)
        run.exit_code = outcome["exit_code"]
        run.stdout = outcome["stdout"]
        run.stderr = outcome["stderr"]
        run.finished_at = time.monotonic()
        if outcome["timed_out"]:
            run.status = "timed_out"
        elif outcome["exit_code"] == 0:
            run.status = "success"
        else:
            run.status = "failed"

    threading.Thread(target=_worker, daemon=True).start()
    return run


if __name__ == "__main__":
    started = time.monotonic()
    outcome = run_full_mission()
    elapsed = time.monotonic() - started
    print(f"--- mission finished in {elapsed:.1f}s ---")
    print(f"exit_code={outcome['exit_code']} timed_out={outcome['timed_out']}")
    print("--- stdout ---")
    print(outcome["stdout"])
    print("--- stderr ---")
    print(outcome["stderr"])
