"""Appends LogEvent records to a JSONL file. Config: logging (owner: person_3).
"""
import json
from dataclasses import asdict
from pathlib import Path

from shared.constants import LOG_OUTPUT_PATH
from shared.models import LogEvent


class Logger:
    def __init__(self, output_path: str = LOG_OUTPUT_PATH):
        self.output_path = output_path

    @staticmethod
    def _to_json_line(event: LogEvent) -> str:
        """Pure conversion, no file I/O - easy to test on its own."""
        return json.dumps(asdict(event)) + "\n"

    def log(self, event: LogEvent) -> None:
        """logging.record: append one LogEvent as one line."""
        Path(self.output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_path, "a", encoding="utf-8") as f:
            f.write(self._to_json_line(event))
