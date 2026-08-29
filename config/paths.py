"""Centralized filesystem paths, resolved absolutely against the repository
root rather than the current working directory.

Before this existed, ai/model_config.py, ai/image_processing.py, and
dashboard/app.py each independently recomputed
`Path(__file__).resolve().parent.parent`, and shared/constants.py's
LOG_OUTPUT_PATH was a bare relative string ("results/mission_log.jsonl")
that only pointed at the right file when a process's current working
directory happened to be the repo root - a silent footgun for anything run
from elsewhere. This module is the one place those paths are defined.

Deliberately NOT used by dashboard/app.py: `streamlit run dashboard/app.py`
puts dashboard/ (not the repo root) on sys.path, so `import config.paths`
isn't reliably importable there. The dashboard already documents itself as
intentionally decoupled from the rest of the source tree (see its own
docstring and dashboard/README.md) and keeps computing its own
`Path(__file__).resolve().parent.parent` for that reason.
"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

CONFIG_PATH = PROJECT_ROOT / "config" / "Green_Guardians_settings.yaml"

RESULTS_DIR = PROJECT_ROOT / "results"
LOG_PATH = RESULTS_DIR / "mission_log.jsonl"
EVIDENCE_DIR = RESULTS_DIR / "images"
VIDEOS_DIR = RESULTS_DIR / "videos"

SAMPLE_DATA_DIR = PROJECT_ROOT / "sample_data"
SCENARIOS_DIR = SAMPLE_DATA_DIR / "scenarios"

MODELS_DIR = PROJECT_ROOT / "models"
PRETRAINED_FALLBACK_MODEL = PROJECT_ROOT / "yolov8n.pt"
