# Person 3 — Backend Checklist

## Phase 1 — Understand the System
*(no ticket — prerequisite groundwork)*
- [x] Studied the full architecture: Drone → Camera → AI → Mission Controller → Alert/Log → Dashboard
- [ ] Draw the diagram yourself
- [x] Understand Person 1's real format — `ai/detector.py`'s `detect(frame, frame_id, timestamp, source)` → list of dicts (`hazard`, `confidence`, `bbox`, `image_width`, `image_height`, `image_path`, `source`)
- [x] Understand Person 2's real format — `drone/drone_controller.py`'s `get_position()` → `(x,y,z)` Webots world-frame, z positive up

## Phase 2 — Data Structures — **BE-01**
*(files: `shared/models.py`, `shared/constants.py`, `shared/interfaces.py`)*
- [x] `Position`, `DetectionInput`, `DroneStatus` (no battery/camera_ok — neither exists in `drone/`), `CameraFrameMetadata`, `NavigationCommand` + `TargetHint`, `InvestigationResult`, `AlertOutput`, `DashboardStatusOutput`, `LogEvent`
- [x] Enums: `MissionState`, `InvestigationStatus`, `Hazard`, `DetectionSource`, `InvestigationOutcome`, `LogEventType`
- [x] `CAMERA_WIDTH`/`CAMERA_HEIGHT` constants
- [x] `DetectorProtocol`, `DroneProtocol`
- [x] Common JSON format defined and kept in sync with real code (`config/Green_Guardians_settings.yaml`)
- [ ] Contract tests — not written yet

## Phase 3 — Mission Controller
- [x] States defined — `MissionState`: `IDLE, TAKEOFF, PATROL, HAZARD_DETECTED, INVESTIGATING, CONFIRMED, REJECTED, RETURN_HOME, LANDING, LANDED, ERROR`
- [x] **BE-02** — State machine logic (`backend/state_machine.py`: `MissionStateMachine`, `TRANSITIONS` table; ERROR recoverable to IDLE)
- [x] **BE-03** — Controller orchestration (`backend/controller.py`: `MissionController.handle_detection()`/`handle_drone_status()`/`get_dashboard_status()`; CONFIRMED/REJECTED->alert/log path deferred to BE-04/06/07)
- [x] **BE-04** — Investigation policy (`backend/controller.py`: `handle_detections()` groups simultaneous candidates via the 3x3-region rule, investigates highest-confidence incident first, stashes rest in `pending_candidates`; `start_investigation()` moves HAZARD_DETECTED->INVESTIGATING, not yet called anywhere since drone/'s investigation maneuver isn't built)
- [x] **BE-05** — Confirmation/timeout rule (`backend/controller.py`: `handle_investigation_observation()` tracks a 3-of-5 confirmation window per `_ActiveInvestigation`, resolves early on 3 positive or 5 checked; `check_investigation_timeout()` force-rejects after 15s with no data - must be called periodically by the future orchestration loop; builds a minimal `AlertOutput` on CONFIRMED, full alert manager still BE-06)

## Phase 4 — Alert System — **BE-06**
- [x] Alert shape defined (`AlertOutput`, includes `observed_position`)
- [x] Alert manager class (`backend/alert_manager.py`: `AlertManager.create_alert()` builds `AlertOutput` from an `InvestigationResult`, tracked in `alert_history`)
- [x] Deduplication logic — replaced the stale time-based `shared_policy.duplicate_rule` (8s, based on since-invalid AirSim waypoint/speed assumptions) with position-based suppression: `AlertManager.is_suppressed()` checks horizontal distance to the last confirmed alert against `POST_ALERT_SUPPRESSION_RADIUS_M` (5m); wired into `MissionController.handle_detection()`

## Phase 5 — Logging — **BE-07**
- [x] Log event shape defined (`LogEvent`, `LogEventType`)
- [x] Logger class (`backend/logger.py`: `Logger.log()` appends one JSON line per `LogEvent`, creates `results/` if missing)
- [x] Writing to `results/mission_log.jsonl` — all 9 log points in `backend/controller.py` wired via the `_log()` helper (rejected/accepted inputs, state changes, investigation results, alerts, errors); `.gitignore` updated so the generated log file itself isn't tracked

## Phase 6 — Integration
- [x] Groundwork laid — `DetectorProtocol`/`DroneProtocol` ready for `controller.py` to type against
- [x] **BE-08**/**BE-09** — `main.py`'s `OrchestrationMission` ties `drone/`, `ai/`, and `backend/` together: patrol loop, detection adapter, investigation sub-loop (`investigate()` + up to 5 fresh-frame checks + timeout), takeoff/land failure handling. Verified with fakes (7 scenarios: happy path, all-reject, multi-detection reduction, move_to/takeoff/land failures) - not yet run against live Webots/a real trained model (Tier 2, needs a live session)

## Phase 7 — Testing
- [ ] Mock scenario files — 5 scenario names exist in config, no files in `sample_data/` yet
- [ ] Controller tests against mocks
- [ ] Full workflow test
- [ ] **BE-10** — End-to-end failure handling

## Phase 8 — Documentation — **BE-11**
- [ ] Nothing written — `docs/` only has `.gitkeep`
