"""Drives each sample_data/scenarios/*.json mock scenario through a real
MissionController and checks the outcome matches the file's declared
expected_outcome. Config: mock_development (owner: person_3).
"""
import pytest

from backend.controller import MissionController
from backend.scenario_runner import discover_scenarios, load_scenario, run_scenario

SCENARIO_PATHS = discover_scenarios()

REQUIRED_SCENARIOS = {
    "no_hazard_continue_patrol",
    "unconfirmed_detection_rejected",
    "confirmed_fire_alert",
    "smoke_false_positive_rejected",
}


def test_all_required_scenarios_present():
    names = {p.stem for p in SCENARIO_PATHS}
    assert REQUIRED_SCENARIOS <= names


@pytest.mark.parametrize("path", SCENARIO_PATHS, ids=lambda p: p.stem)
def test_scenario_matches_expected_outcome(path, tmp_path):
    scenario = load_scenario(path)
    controller = MissionController()
    # Keep test runs off the real results/ log, same convention as
    # test_controller.py / test_orchestration.py.
    controller.logger.output_path = str(tmp_path / "mission_log.jsonl")

    summary = run_scenario(path, controller=controller)

    expected = scenario["expected_outcome"]
    assert summary["investigation_triggered"] == expected["investigation_triggered"]
    assert summary["investigation_result"] == expected["investigation_result"]
    assert summary["final_mission_state"] == expected["final_mission_state"]
    assert summary["alert_created"] == expected["alert_created"]
    assert summary["confirmed_alert_count"] == expected["confirmed_alert_count"]
