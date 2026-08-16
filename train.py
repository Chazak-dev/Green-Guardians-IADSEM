"""Fine-tunes YOLOv8n on the fire/smoke dataset. Standalone script, not part
of the ai/ package - training is a one-off developer action, not something
the detector needs at runtime.

Hyperparameters match the Phase 4 baseline agreed for this run: epochs=100
with patience=20 for early stopping (rather than running the full 100
blindly), imgsz=640 to match config/Green_Guardians_settings.yaml's ai:
baseline, seed fixed for a reproducible run to compare future tuning
against. device defaults to "cpu" - this machine has no CUDA GPU
(torch.cuda.is_available() == False).
"""
import argparse

from ultralytics import YOLO

DEFAULT_DATA = r"C:\Users\itsch\Desktop\datasets\real\fire_smoke\data.yaml"


def parse_args():
    parser = argparse.ArgumentParser(description="Fine-tune YOLOv8n on the fire/smoke dataset.")
    parser.add_argument("--data", default=DEFAULT_DATA, help="Path to data.yaml")
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--patience", type=int, default=20, help="Early-stop after N epochs with no mAP improvement")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--seed", type=int, default=0)
    return parser.parse_args()


def main():
    args = parse_args()
    model = YOLO("yolov8n.pt")
    model.train(
        data=args.data,
        epochs=args.epochs,
        patience=args.patience,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        seed=args.seed,
        save_period=-1,  # only best.pt/last.pt, not a checkpoint every epoch
    )


if __name__ == "__main__":
    main()
