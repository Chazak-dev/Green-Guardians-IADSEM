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

## Project Structure

ai/
drone/
backend/
dashboard/
shared/
config/

