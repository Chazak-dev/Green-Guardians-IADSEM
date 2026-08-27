import json

from backend.logger import Logger
from shared.models import LogEvent


def _event(**overrides) -> LogEvent:
    fields = dict(
        event_id="event-1",
        timestamp="2026-08-15T10:00:00Z",
        event_type="STATE_CHANGE",
        message="PATROL -> HAZARD_DETECTED",
        mission_state="HAZARD_DETECTED",
        detection_id=None,
        investigation_id=None,
        alert_id=None,
        details=None,
    )
    fields.update(overrides)
    return LogEvent(**fields)


def test_log_appends_one_json_line(tmp_path):
    output_path = tmp_path / "results" / "mission_log.jsonl"
    logger = Logger(output_path=str(output_path))

    logger.log(_event())

    lines = output_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["event_id"] == "event-1"
    assert record["event_type"] == "STATE_CHANGE"


def test_log_creates_parent_directory(tmp_path):
    output_path = tmp_path / "nested" / "dir" / "mission_log.jsonl"
    Logger(output_path=str(output_path)).log(_event())
    assert output_path.exists()


def test_log_appends_across_multiple_calls(tmp_path):
    output_path = tmp_path / "mission_log.jsonl"
    logger = Logger(output_path=str(output_path))

    logger.log(_event(event_id="event-1"))
    logger.log(_event(event_id="event-2"))

    lines = output_path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["event_id"] for line in lines] == ["event-1", "event-2"]


def test_to_json_line_is_pure_and_newline_terminated():
    line = Logger._to_json_line(_event())
    assert line.endswith("\n")
    assert json.loads(line)["message"] == "PATROL -> HAZARD_DETECTED"
