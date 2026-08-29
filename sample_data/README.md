# sample_data/

Mock inputs for developing and demoing the backend (`backend/`) without
Webots or a trained YOLO model running. Owner: Person 3
(`config/Green_Guardians_settings.yaml`'s `mock_development` section).

## Scenarios (`scenarios/*.json`)

Each file is a scripted sequence of `DetectionInput`-shaped frames, driven
through a real `MissionController` (not a separate mock implementation) via
`backend/scenario_runner.py`. That mirrors exactly the API `main.py`'s
`OrchestrationMission` uses for a live mission: `handle_detections()` ->
`start_investigation()` -> `handle_investigation_observation()` per fresh
frame -> `resume_patrol()`.

| File | What it proves |
|---|---|
| `no_hazard_continue_patrol.json` | Low-confidence noise and an empty frame never create a candidate; the mission stays in `PATROL`. |
| `unconfirmed_detection_rejected.json` | A fire candidate opens an investigation, but confidence never reaches the 0.65 confirmation threshold in the 5-frame window - `REJECTED`. |
| `confirmed_fire_alert.json` | A fire candidate is confirmed after 3 of 5 fresh frames clear 0.65 confidence - exactly one alert is created. |
| `smoke_false_positive_rejected.json` | A smoke reading crosses the trigger threshold but doesn't hold up under investigation - `REJECTED` (a false positive). |

Each file's `expected_outcome` field is the source of truth both the CLI and
`tests/test_sample_scenarios.py` check the real run against - if you edit a
scenario's detection sequence, update `expected_outcome` to match.

## Running them

Populate `results/mission_log.jsonl` (and therefore the dashboard - see
`dashboard/README.md`) with one scenario:

```
python run_scenario.py confirmed_fire_alert
```

...or all four, one after another (each gets its own fresh
`MissionController`, so nothing suppresses or interferes across scenarios):

```
python run_scenario.py --all
```

Each run prints a JSON summary (triggered / result / final state / alert
count) to stdout in addition to writing the log.

## Tests

```
pytest tests/test_sample_scenarios.py -v
```

Replays every file in `scenarios/` (against a temp log path, not the real
`results/`) and asserts the resulting mission state, investigation result,
and alert count match that file's `expected_outcome`.
