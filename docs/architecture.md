# Green Guardians — Architecture

This documents how the pieces that already exist in this repository fit
together. It describes the real, implemented code (as of the `main.py`
`OrchestrationMission` orchestration loop), not the project's original
aspirational design — see `config/Green_Guardians_settings.yaml` for the
authoritative contracts and policy values referenced throughout.

## 1. Component overview

```mermaid
graph TD
    subgraph Sim["Webots simulation"]
        WB["green_guardians_patrol.wbt<br/>DJI Mavic 2 Pro, extern controller"]
    end

    subgraph DroneMod["drone/ (Person 2)"]
        DC["drone_controller.py<br/>DroneController"]
        CAM["camera.py<br/>DroneCamera"]
    end

    subgraph AIMod["ai/ (Person 1)"]
        DET["detector.py<br/>FireSmokeDetector"]
        IMG["image_processing.py<br/>validate / annotate / save evidence"]
        MC["model_config.py<br/>ModelConfig from YAML"]
        WEIGHTS[("models/fire_smoke.pt<br/>YOLOv8n")]
    end

    subgraph BackendMod["backend/ (Person 3)"]
        CTRL["controller.py<br/>MissionController"]
        SM["state_machine.py<br/>MissionStateMachine"]
        AM["alert_manager.py<br/>AlertManager"]
        LOG["logger.py<br/>Logger"]
    end

    subgraph SharedMod["shared/"]
        MODELS["models.py — dataclasses"]
        CONST["constants.py — enums + thresholds"]
        IFACE["interfaces.py — Protocols"]
    end

    MAIN["main.py<br/>OrchestrationMission"]
    CFG[("config/Green_Guardians_settings.yaml")]
    RESULTS[("results/mission_log.jsonl<br/>results/images/")]
    DASH["dashboard/app.py<br/>Streamlit (Person 4)"]

    WB <--> DC
    DC --- CAM
    MAIN --> DC
    MAIN --> DET
    MAIN --> CTRL
    CAM -- "frame + metadata" --> MAIN
    MAIN -- "frame" --> DET
    DET --> IMG
    DET --> MC
    MC --> WEIGHTS
    DET -- "detection_event dicts" --> MAIN
    MAIN -- "DetectionInput" --> CTRL
    CTRL --> SM
    CTRL --> AM
    CTRL --> LOG
    LOG --> RESULTS
    IMG -- "evidence .jpg" --> RESULTS
    CFG -.->|"thresholds, routes, policy"| CTRL
    CFG -.-> MC
    CFG -.-> DASH
    RESULTS --> DASH
    CTRL -.-> MODELS
    CTRL -.-> CONST
    CTRL -.->|"duck-typed against"| IFACE
```

**Key architectural fact**: `dashboard/app.py` and `main.py` are **separate
processes**. There is no HTTP API or IPC layer between them — the project is
a single Python application whose only cross-process channel is the
filesystem. The dashboard is deliberately read-only: it polls
`results/mission_log.jsonl`, `results/images/`, and
`config/Green_Guardians_settings.yaml` on a timer (`st.fragment(run_every=…)`);
it never sees `MissionController`'s live in-memory state directly. See
`dashboard/README.md` for the reasoning.

## 2. Data flow for one hazard cycle

This traces `main.py`'s `OrchestrationMission._run_waypoint()` /
`_investigate()` — the actual live loop — for one patrol leg that turns into
a confirmed (or rejected) hazard.

```mermaid
sequenceDiagram
    participant M as main.py<br/>OrchestrationMission
    participant D as DroneController
    participant A as FireSmokeDetector
    participant C as MissionController
    participant AM as AlertManager
    participant L as Logger

    M->>D: move_to(x, y, z)
    M->>D: get_position()
    M->>C: handle_drone_status(DroneStatus)
    M->>D: camera.capture_frame_metadata()
    M->>A: detect(frame, source="patrol")
    A-->>M: [detection_event, ...]
    M->>C: handle_detections([DetectionInput])

    alt confidence >= 0.60 (candidate_trigger)
        C->>C: PATROL -> HAZARD_DETECTED
        C-->>M: True (triggered)
        M->>C: start_investigation()
        C->>C: HAZARD_DETECTED -> INVESTIGATING
        M->>D: investigate(target_hint)
        D-->>M: holding position (nudged toward the hazard)

        loop up to 5 fresh frames
            M->>D: camera.capture_frame_metadata()
            M->>A: detect(frame, source="investigation")
            A-->>M: detection or none
            M->>C: handle_investigation_observation(detection)
            C->>C: tally positive / checked
        end

        alt >=3 of 5 positive, same hazard, conf >= 0.65
            C->>C: INVESTIGATING -> CONFIRMED
            C->>AM: create_alert(InvestigationResult, position)
            AM-->>C: AlertOutput
            C->>L: log ALERT_CREATED (+ INVESTIGATION_RESULT)
        else 5 checked without confirming
            C->>C: INVESTIGATING -> REJECTED
            C->>L: log INVESTIGATION_RESULT
        end

        M->>C: resume_patrol()
        C->>C: -> PATROL
    end
```

Every state transition, accepted/rejected input, investigation result, and
alert also gets written as one `LogEvent` JSON line to
`results/mission_log.jsonl` via `backend/logger.py` — that file is the only
record of a mission run that outlives the process, and it's what the
dashboard reads.

## 3. Module responsibilities

| Module | Owner | Responsibility |
|---|---|---|
| `drone/drone_controller.py`, `drone/camera.py` | Person 2 | Webots extern-controller flight, GPS position, camera frames |
| `ai/detector.py`, `ai/image_processing.py`, `ai/model_config.py` | Person 1 | YOLOv8n fire/smoke inference, evidence-image annotation/saving |
| `backend/controller.py`, `state_machine.py`, `alert_manager.py`, `logger.py` | Person 3 | Mission state machine, candidate/investigation/confirmation policy, alert dedup, JSONL logging |
| `main.py` | Person 3 | `OrchestrationMission` — the live loop tying drone/ai/backend together |
| `shared/models.py`, `constants.py`, `interfaces.py` | Person 3 | Dataclass contracts, enums/thresholds, structural `Protocol`s so `backend/` doesn't import `ai/`/`drone/` directly |
| `dashboard/app.py` | Person 4 | Streamlit visualization of the persisted mission log, evidence images, and config — read-only, separate process |
| `config/Green_Guardians_settings.yaml` | Person 3 (shared) | The single source of truth for thresholds, routes, and contract shapes every module is written against |

## 4. Where the contracts live

`config/Green_Guardians_settings.yaml`'s `contracts:` and
`backend_contracts:` sections describe each JSON-shaped object that crosses
a module boundary (`DetectionInput`, `DroneStatus`, `AlertOutput`,
`DashboardStatusOutput`, `LogEvent`, …). `shared/models.py` is the Python
dataclass mirror of those shapes, and `shared/constants.py` mirrors the
enums and numeric thresholds (`CANDIDATE_TRIGGER_THRESHOLD`,
`CONFIRMATION_*`, `POST_ALERT_SUPPRESSION_RADIUS_M`, …) so nothing drifts
between the YAML documentation and the running code.

## 5. Deliberate limitations (not bugs)

- **No real GPS/3-D geolocation.** `drone.investigation_maneuver`'s
  `target_hint` is a rough left/center/right bbox-based nudge, not a
  computed hazard position. See `investigation.out_of_scope` in the config.
- **Coordinates are Webots world-frame metres, not AirSim NED.** The project
  switched simulators from AirSim to Webots after the config file's
  coordinate examples were first written; `z` is altitude and is positive
  up everywhere in this codebase (`Position`, `DroneStatus`, `AlertOutput`).
- **The dashboard cannot see live in-memory state.** See §1 above — this is
  a conscious trade-off to avoid coupling two processes over an ad hoc
  channel, not a missing feature.

## 6. Running the system

- **Full live mission** (needs Webots running with
  `drone/webots_world/green_guardians_patrol.wbt` loaded, and ideally a
  trained `models/fire_smoke.pt`): `python main.py`
- **Backend only, no Webots/model needed**: replay a scripted scenario
  through the real `MissionController` — see `sample_data/README.md`.
- **Dashboard**: `streamlit run dashboard/app.py` (reads whatever's already
  in `results/`) — see `dashboard/README.md`.
- **Tests**: `pytest`
