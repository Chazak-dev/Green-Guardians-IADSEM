"""Fine-tunes YOLOv8n on the fire/smoke dataset. Standalone script, not part
of the ai/ package - training is a one-off developer action, not something
the detector needs at runtime.

Hyperparameters match the Phase 4 baseline agreed for this run: epochs=10
with patience=20 for early stopping (patience exceeds epochs, so early
stopping is effectively a no-op unless --epochs is raised for a longer run),
imgsz=640 to match config/Green_Guardians_settings.yaml's ai: baseline, seed
fixed for a reproducible run to compare future tuning against.

--weights and --device both auto-detect the right choice by default instead
of requiring you to remember flags every run - a run was accidentally
trained from the raw COCO checkpoint on CPU because those flags were
forgotten, silently discarding all prior real-photo training and skipping
the GPU. Pass either explicitly to override the auto-detected default.
"""
import argparse

import torch
from ultralytics import YOLO

from config.paths import MODELS_DIR, PRETRAINED_FALLBACK_MODEL

DEFAULT_DATA = r"C:\Users\itsch\Desktop\datasets\real\fire_smoke\data.yaml"
_FINE_TUNED_WEIGHTS = MODELS_DIR / "fire_smoke.pt"


def _default_weights() -> str:
    """Continue from the already fine-tuned model if it exists (keeps what
    it already learned from real photos), otherwise fall back to the raw
    COCO checkpoint - same fallback rule ai/model_config.py already uses."""
    return str(_FINE_TUNED_WEIGHTS) if _FINE_TUNED_WEIGHTS.exists() else str(PRETRAINED_FALLBACK_MODEL)


def _default_device() -> str:
    """GPU if one's actually visible to PyTorch, CPU otherwise - no more
    silently training on CPU because --device wasn't passed."""
    return "0" if torch.cuda.is_available() else "cpu"


def parse_args():
    parser = argparse.ArgumentParser(description="Fine-tune YOLOv8n on the fire/smoke dataset.")
    parser.add_argument("--data", default=DEFAULT_DATA, help="Path to data.yaml")
    parser.add_argument("--weights", default=None,
                         help="Starting weights. Defaults to models/fire_smoke.pt if it exists (continuing "
                              "training), otherwise the untrained yolov8n.pt COCO checkpoint.")
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--patience", type=int, default=20, help="Early-stop after N epochs with no mAP improvement")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--device", default=None,
                         help="Defaults to GPU 0 if CUDA is available, otherwise cpu.")
    parser.add_argument("--seed", type=int, default=0)
    return parser.parse_args()


def main():
    args = parse_args()
    weights = args.weights or _default_weights()
    device = args.device or _default_device()
    print(f"Training from weights={weights!r} on device={device!r} (pass --weights/--device to override)")

    model = YOLO(weights)
    model.train(
        data=args.data,
        epochs=args.epochs,
        patience=args.patience,
        imgsz=args.imgsz,
        batch=args.batch,
        device=device,
        seed=args.seed,
        save_period=-1,  # only best.pt/last.pt, not a checkpoint every epoch
    )


if __name__ == "__main__":
    main()
