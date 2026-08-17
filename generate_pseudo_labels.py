"""Batch inference over an unlabeled image folder, exporting YOLO-format
prediction labels for human review.

One-off tooling for the virtual (simulator) dataset milestone: Person 2's
simulator images have no labels yet. This uses Person 1's trained fire/smoke
weights to auto-generate a first pass of YOLO labels, which a human then
reviews/corrects before deciding whether the virtual dataset is worth
retraining on. Standalone script, not part of the ai/ package - like
train.py, this is a developer action, not something FireSmokeDetector needs
at runtime.

Usage (see README for the full walkthrough):
    python generate_pseudo_labels.py --source path/to/sim_images --output path/to/output_dataset
"""
import argparse
import shutil
from pathlib import Path

from ultralytics import YOLO

from ai.model_config import load_model_config

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate YOLO-format pseudo-labels for a folder of unlabeled images."
    )
    parser.add_argument("--source", required=True, help="Folder of input images to run inference on")
    parser.add_argument("--output", required=True, help="Folder to write the resulting images/labels dataset into")
    parser.add_argument("--weights", default=None,
                         help="Path to trained weights. Defaults to config/Green_Guardians_settings.yaml's "
                              "ai.model_path (models/fire_smoke.pt), same as the live detector.")
    parser.add_argument("--conf", type=float, default=None,
                         help="Confidence threshold for keeping a detection. Defaults to the config's "
                              "ai.confidence_threshold.")
    parser.add_argument("--iou", type=float, default=None,
                         help="IoU threshold for NMS. Defaults to the config's ai.iou_threshold.")
    parser.add_argument("--imgsz", type=int, default=None,
                         help="Inference image size. Defaults to the config's ai.imgsz.")
    parser.add_argument("--device", default=None, help="'cpu', '0', etc. Defaults to auto-detect (GPU if available).")
    parser.add_argument("--save-images", action="store_true",
                         help="Also save annotated preview images (boxes drawn) alongside the labels")
    return parser.parse_args()


def main():
    args = parse_args()
    model_config = load_model_config()

    weights_path = Path(args.weights) if args.weights else model_config.model_path
    conf = args.conf if args.conf is not None else model_config.confidence_threshold
    iou = args.iou if args.iou is not None else model_config.iou_threshold
    imgsz = args.imgsz if args.imgsz is not None else model_config.imgsz

    if args.weights is None and weights_path.name == "yolov8n.pt":
        print(
            f"WARNING: no fine-tuned weights found at the configured path "
            f"({model_config.model_path.parent / 'fire_smoke.pt'}); falling back to the untrained "
            f"COCO checkpoint '{weights_path}'. Pseudo-labels from this model will NOT be fire/smoke "
            f"specific. Pull the latest repo (models/fire_smoke.pt should be committed) or pass "
            f"--weights explicitly."
        )

    source_dir = Path(args.source)
    if not source_dir.is_dir():
        raise SystemExit(f"Source folder not found: {source_dir}")

    source_images = sorted(
        p for p in source_dir.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )
    if not source_images:
        raise SystemExit(f"No images found in {source_dir}")

    output_dir = Path(args.output)
    images_dir = output_dir / "images"
    labels_dir = output_dir / "labels"
    preview_dir = output_dir / "predictions_preview"

    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    for image_path in source_images:
        shutil.copy2(image_path, images_dir / image_path.name)

    model = YOLO(str(weights_path))

    predict_kwargs = dict(
        source=str(source_dir),
        conf=conf,
        iou=iou,
        imgsz=imgsz,
        save=args.save_images,
        save_txt=True,
        save_conf=True,
        project=str(output_dir),
        name="_yolo_predict",
        exist_ok=True,
        stream=True,
        verbose=False,
    )
    if args.device:
        predict_kwargs["device"] = args.device

    processed = 0
    for _ in model.predict(**predict_kwargs):
        processed += 1

    yolo_run_dir = output_dir / "_yolo_predict"
    yolo_labels_dir = yolo_run_dir / "labels"

    # Ensure every image has a matching .txt (empty if nothing was detected
    # above threshold), so images/ and labels/ line up 1:1.
    for image_path in source_images:
        generated_label = yolo_labels_dir / f"{image_path.stem}.txt"
        target_label = labels_dir / f"{image_path.stem}.txt"
        if generated_label.exists():
            shutil.move(str(generated_label), str(target_label))
        else:
            target_label.touch()

    if args.save_images:
        preview_dir.mkdir(parents=True, exist_ok=True)
        for item in yolo_run_dir.iterdir():
            if item.is_file() and item.suffix.lower() in IMAGE_EXTENSIONS:
                shutil.move(str(item), str(preview_dir / item.name))

    shutil.rmtree(yolo_run_dir, ignore_errors=True)

    # Each label line is "class x_center y_center width height confidence"
    # (save_conf=True appends confidence as a 6th column) - normal YOLO
    # training expects 5 columns, so strip the confidence column after
    # manual review, before this becomes a training dataset.
    classes_path = output_dir / "classes.txt"
    with open(classes_path, "w", encoding="utf-8") as f:
        for idx in sorted(model.names):
            f.write(f"{model.names[idx]}\n")

    print(f"Processed {processed} images from {source_dir}")
    print(f"Weights used: {weights_path}")
    print(f"Images:  {images_dir}")
    print(f"Labels:  {labels_dir} (5 geometry columns + 1 trailing confidence column per line)")
    print(f"Classes: {classes_path}")
    if args.save_images:
        print(f"Preview: {preview_dir}")


if __name__ == "__main__":
    main()
