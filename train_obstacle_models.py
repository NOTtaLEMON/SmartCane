"""
============================================================================
 SMART CANE CLIP-ON  |  Train Separate Obstacle Detection Models
============================================================================
 Trains 3 individual YOLOv8n detection models, one per obstacle class:
   1. tree
   2. electric_pole
   3. steps_kerb  (classes: object, stairs)

 Each model is small (YOLOv8n) and exported to TFLite float16 at 320px,
 so all three can be bundled into the Android app.

 OUTPUT (per model)
 ------------------
   runs/detect/tree/weights/best.pt
   runs/detect/electric_pole/weights/best.pt
   runs/detect/steps_kerb/weights/best.pt
   models/tree_float16.tflite
   models/electric_pole_float16.tflite
   models/steps_kerb_float16.tflite

 USAGE
 -----
   python train_obstacle_models.py                  # train all three
   python train_obstacle_models.py --model tree     # train one only
   python train_obstacle_models.py --epochs 100 --batch 16
   python train_obstacle_models.py --no-export      # skip TFLite export

 REQUIREMENTS
 ------------
   pip install ultralytics tensorflow  (Python <= 3.12 for TF)
============================================================================
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from ultralytics import YOLO

BASE_DATA = Path("data/raw")
OUT_MODELS = Path("models")

_ROOT = Path(__file__).resolve().parent

OBSTACLE_CONFIGS = {
    "tree": {
        "data": BASE_DATA / "tree" / "data.yaml",
        "classes": ["tree"],
        "project": str(_ROOT / "runs" / "detect" / "tree"),
    },
    "electric_pole": {
        "data": BASE_DATA / "electric_pole" / "data.yaml",
        "classes": ["electric_pole"],
        "project": str(_ROOT / "runs" / "detect" / "electric_pole"),
    },
    "steps_kerb": {
        "data": BASE_DATA / "steps_kerb" / "data.yaml",
        "classes": ["object", "stairs"],
        "project": str(_ROOT / "runs" / "detect" / "steps_kerb"),
    },
    "cars": {
        "data": BASE_DATA / "cars" / "data.yaml",
        "classes": ["1", "2", "3", "4", "5"],
        "project": str(_ROOT / "runs" / "detect" / "cars"),
    },
}


def fix_data_yaml(yaml_path: Path) -> Path:
    """
    Roboflow data.yaml uses relative paths like '../train/images'.
    Rewrite them to absolute paths so training works from any cwd.
    Returns path to a patched copy in the same directory.
    """
    import yaml

    patched_path = yaml_path.parent / "data_abs.yaml"
    with open(yaml_path) as f:
        cfg = yaml.safe_load(f)

    base = yaml_path.parent
    for split in ("train", "val", "test"):
        if split in cfg:
            rel = cfg[split]
            abs_path = (base / rel).resolve()
            if abs_path.exists():
                cfg[split] = str(abs_path)

    with open(patched_path, "w") as f:
        yaml.dump(cfg, f)

    return patched_path


def train_model(name: str, cfg: dict, epochs: int, batch: int, imgsz: int, device: str) -> Path:
    """Train a single YOLOv8n detection model and return path to best.pt."""
    print(f"\n{'='*60}")
    print(f"  Training: {name}  |  classes: {cfg['classes']}")
    print(f"{'='*60}\n")

    data_yaml = fix_data_yaml(cfg["data"])

    model = YOLO("yolov8n.pt")  # pretrained nano backbone
    results = model.train(
        data=str(data_yaml),
        epochs=epochs,
        batch=batch,
        imgsz=imgsz,
        project=cfg["project"],
        name="train",
        exist_ok=True,
        device=device,
        patience=30,
        cache=False,
        verbose=True,
    )

    best_pt = Path(cfg["project"]) / "train" / "weights" / "best.pt"
    if not best_pt.exists():
        # fallback for older ultralytics versions
        best_pt = Path(cfg["project"]) / "weights" / "best.pt"

    print(f"\n  Best weights saved: {best_pt}")
    return best_pt


def export_tflite(pt_path: Path, name: str, imgsz: int) -> Path:
    """Export best.pt to TFLite float16 and copy to models/."""
    print(f"\n  Exporting {name} → TFLite float16 ...")

    model = YOLO(str(pt_path))
    model.export(
        format="tflite",
        imgsz=imgsz,
        half=True,      # float16
        int8=False,
        nms=False,      # handle NMS in app
    )

    # ultralytics saves alongside the .pt file
    tflite_candidates = list(pt_path.parent.glob("*.tflite"))
    if not tflite_candidates:
        # try saved_model subfolder
        tflite_candidates = list(pt_path.parent.glob("**/*.tflite"))

    OUT_MODELS.mkdir(exist_ok=True)

    if tflite_candidates:
        src = tflite_candidates[0]
        dst = OUT_MODELS / f"{name}_float16.tflite"
        shutil.copy2(src, dst)
        print(f"  TFLite saved: {dst}")
        return dst
    else:
        print("  WARNING: TFLite file not found after export.")
        return pt_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Train separate obstacle detection models")
    parser.add_argument(
        "--model",
        choices=list(OBSTACLE_CONFIGS.keys()) + ["all"],
        default="all",
        help="Which model to train (default: all)",
    )
    parser.add_argument("--epochs", type=int, default=80, help="Training epochs (default 80)")
    parser.add_argument("--batch",  type=int, default=16, help="Batch size (default 16)")
    parser.add_argument("--imgsz",  type=int, default=320, help="Image size (default 320 for mobile)")
    parser.add_argument("--device", default="",  help="cuda / cpu / 0 (auto if blank)")
    parser.add_argument("--no-export", dest="export", action="store_false", help="Skip TFLite export")
    args = parser.parse_args()

    targets = list(OBSTACLE_CONFIGS.keys()) if args.model == "all" else [args.model]

    trained = {}
    for name in targets:
        cfg = OBSTACLE_CONFIGS[name]
        if not cfg["data"].exists():
            print(f"  SKIP {name}: data.yaml not found at {cfg['data']}")
            continue
        best_pt = train_model(name, cfg, args.epochs, args.batch, args.imgsz, args.device)
        trained[name] = best_pt

    if args.export:
        for name, pt_path in trained.items():
            if pt_path.exists():
                export_tflite(pt_path, name, args.imgsz)
            else:
                print(f"  SKIP export {name}: {pt_path} not found")

    print("\n\nAll done! TFLite models saved to: models/")
    print("Copy them to: android-app/app/src/main/assets/\n")


if __name__ == "__main__":
    main()
