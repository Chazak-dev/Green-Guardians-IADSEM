"""Model and inference settings for the AI detection module.

Reads the frozen `ai:` baselines from config/Green_Guardians_settings.yaml
at load time so this module never drifts from values the rest of the team
was told about.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import yaml

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SETTINGS_PATH = _PROJECT_ROOT / "config" / "Green_Guardians_settings.yaml"
_PRETRAINED_FALLBACK = _PROJECT_ROOT / "yolov8n.pt"


@dataclass(frozen=True)
class ModelConfig:
    model_path: Path
    classes: List[str]
    imgsz: int
    iou_threshold: float
    device: Optional[str]
    inference_fps_target: int
    confidence_threshold: float


def load_model_config(settings_path: Path = _SETTINGS_PATH) -> ModelConfig:
    with open(settings_path, "r", encoding="utf-8") as f:
        settings = yaml.safe_load(f)

    ai_settings = settings["ai"]

    # models/fire_smoke.pt is the target once fine-tuned; until it exists,
    # run the pipeline against the pretrained COCO weights as planned.
    configured_path = _PROJECT_ROOT / ai_settings["model_path"]
    model_path = configured_path if configured_path.exists() else _PRETRAINED_FALLBACK

    device = ai_settings["device"]
    resolved_device = None if device == "auto" else device

    return ModelConfig(
        model_path=model_path,
        classes=[c.lower() for c in ai_settings["classes"]],
        imgsz=ai_settings["imgsz"],
        iou_threshold=ai_settings["iou_threshold"],
        device=resolved_device,
        inference_fps_target=ai_settings["inference_fps_target"],
        confidence_threshold=ai_settings["confidence_threshold"],
    )
