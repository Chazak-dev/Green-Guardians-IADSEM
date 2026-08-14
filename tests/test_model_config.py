from ai.model_config import load_model_config


def test_matches_shared_ai_baselines():
    config = load_model_config()

    assert config.classes == ["fire", "smoke"]
    assert config.imgsz == 640
    assert config.iou_threshold == 0.45
    assert config.inference_fps_target == 2


def test_selected_model_path_exists_on_disk():
    config = load_model_config()

    assert config.model_path.exists()
