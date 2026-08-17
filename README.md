# Green-Guardians-IADSEM

# Green Guardians

An AI-powered autonomous drone system for real-time wildfire monitoring.

## Technologies

- Python 3.11.9
- YOLOv8n
- OpenCV
- PyTorch
- AirSim
- Unreal Engine 5
- Streamlit
- Git & GitHub

## Team

Person 1 – AI & Computer Vision

Person 2 – Drone Navigation

Person 3 – Backend & Mission Controller

Person 4 – Dashboard

## Dataset

Real-life fire/smoke training data: [Fire and Smoke Dataset (Object Detection, YOLO)](https://www.kaggle.com/datasets/azimjaan21/fire-and-smoke-dataset-object-detection-yolo?resource=download) — Kaggle, ~17.5k images, YOLO-format labels, `fire`/`smoke` classes. Used to fine-tune YOLOv8n in `ai/` on top of Webots simulation data.

The fine-tuned production weights live at `models/fire_smoke.pt` (promoted from `runs/detect/train-6/weights/best.pt`, the full 100-epoch run). `ai/model_config.py` loads this automatically; it only falls back to the untrained `yolov8n.pt` COCO checkpoint if `models/fire_smoke.pt` is missing.

## Virtual dataset pseudo-labeling

`generate_pseudo_labels.py` runs the trained model over a folder of unlabeled (e.g. simulator) images and exports YOLO-format prediction labels for human review — see the script's `--help` for options. It is standalone, takes no hardcoded paths, and is meant to be run on a machine with a GPU:

```bash
python generate_pseudo_labels.py --source path/to/sim_images --output path/to/output_dataset --save-images
```

## Project Structure

ai/
drone/
backend/
dashboard/
shared/
config/

