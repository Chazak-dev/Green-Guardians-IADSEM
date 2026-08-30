"""Fine-tunes YOLOv8n on the fire/smoke dataset. Standalone script, not part
of the ai/ package - training is a one-off developer action, not something
the detector needs at runtime.

Defaults match tonight's combined real+sim run (see combined_data.yaml.example
and the conversation): --data=combined_data.yaml, --weights=
models/fire_smoke_real_only.pt (the preserved real-photo-only checkpoint -
NOT models/fire_smoke.pt, which is currently the sim-only train-11 model
that already lost real-photo detection; starting from it here would repeat
that same mistake), --epochs=100, --batch=16. imgsz=640 matches
config/Green_Guardians_settings.yaml's ai: baseline. --device auto-detects
GPU vs CPU on its own - no need to pass it.

Plain `python train.py` now runs this exact recipe with no flags needed.
Pass any flag explicitly to override its default for a different run.
"""
import argparse

import torch
from ultralytics import YOLO

from config.paths import MODELS_DIR

DEFAULT_DATA = "combined_data.yaml"
DEFAULT_WEIGHTS = str(MODELS_DIR / "fire_smoke_real_only.pt")


def _default_device() -> str:
    """GPU if one's actually visible to PyTorch, CPU otherwise - no more
    silently training on CPU because --device wasn't passed."""
    return "0" if torch.cuda.is_available() else "cpu"


def parse_args():
    parser = argparse.ArgumentParser(description="Fine-tune YOLOv8n on the fire/smoke dataset.")
    parser.add_argument("--data", default=DEFAULT_DATA, help="Path to data.yaml")
    parser.add_argument("--weights", default=DEFAULT_WEIGHTS, help="Starting weights")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--patience", type=int, default=20, help="Early-stop after N epochs with no mAP improvement")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--device", default=None,
                         help="Defaults to GPU 0 if CUDA is available, otherwise cpu.")
    parser.add_argument("--seed", type=int, default=0)
    return parser.parse_args()


def main():
    args = parse_args()
    device = args.device or _default_device()
    print(f"Training from weights={args.weights!r} on data={args.data!r}, device={device!r} "
          f"(pass --weights/--data/--device to override)")

    model = YOLO(args.weights)
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
