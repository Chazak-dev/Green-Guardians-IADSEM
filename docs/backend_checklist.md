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
- [ ] **BE-03** — Controller orchestration (`backend/controller.py` empty)
- [ ] **BE-04** — Investigation policy (`shared_policy.candidate_trigger`/`simultaneous_detections` — documented, not coded)
- [ ] **BE-05** — Confirmation/timeout rule (`shared_policy.confirmation`/`backend_policy.investigation` — documented, not coded)

## Phase 4 — Alert System — **BE-06**
- [x] Alert shape defined (`AlertOutput`, includes `observed_position`)
- [ ] Alert manager class (`backend/alert_manager.py` empty)
- [ ] Deduplication logic (`backend_policy.alerting.duplicate_rule` — documented, not coded)

## Phase 5 — Logging — **BE-07**
- [x] Log event shape defined (`LogEvent`, `LogEventType`)
- [ ] Logger class (`backend/logger.py` empty)
- [ ] Writing to `results/mission_log.jsonl` — not implemented

## Phase 6 — Integration
- [x] Groundwork laid — `DetectorProtocol`/`DroneProtocol` ready for `controller.py` to type against
- [ ] **BE-08** — Integrate real `FireSmokeDetector` from `ai/detector.py`
- [ ] **BE-09** — Integrate real `DroneController` from `drone/drone_controller.py`

## Phase 7 — Testing
- [ ] Mock scenario files — 5 scenario names exist in config, no files in `sample_data/` yet
- [ ] Controller tests against mocks
- [ ] Full workflow test
- [ ] **BE-10** — End-to-end failure handling

## Phase 8 — Documentation — **BE-11**
- [ ] Nothing written — `docs/` only has `.gitkeep`
