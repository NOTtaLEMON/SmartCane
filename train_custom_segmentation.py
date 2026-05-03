"""
============================================================================
 SMART CANE CLIP-ON  |  Custom YOLOv8 Segmentation Model Training
============================================================================
 Train a custom YOLOv8 segmentation model for Smart Cane obstacle detection.
 
 Detects:
   - person, furniture, vehicle, animal
   - potholes, water puddles, slippery floors
   - clear path (negative class for safety)
 
 DATASET STRUCTURE
 -----------------
 data/
   ├── images/
   │   ├── train/    (80% of images)
   │   ├── val/      (10% of images)
   │   └── test/     (10% of images)
   └── labels/
       ├── train/    (YOLO format .txt with polygon coords)
       ├── val/
       └── test/
 
 LABEL FORMAT (YOLO Segmentation)
 --------------------------------
 Each image has a corresponding .txt file with format:
 <class_id> <x1> <y1> <x2> <y2> ... (normalized 0-1 polygon coordinates)
 
 USAGE
 -----
   python train_custom_segmentation.py
   python train_custom_segmentation.py --epochs 100 --batch 16
   python train_custom_segmentation.py --epochs 200 --batch 32 --resume
 
 REQUIREMENTS
 -----------
   pip install ultralytics opencv-python pyyaml
============================================================================
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from ultralytics import YOLO
import yaml


# Smart Cane Custom Classes
CLASSES = [
    "person",           # 0 - human obstacle
    "furniture",        # 1 - chair, table, couch, bed, etc
    "vehicle",          # 2 - car, truck, motorcycle, bicycle
    "animal",           # 3 - dog, cat, other animals
    "pothole",          # 4 - road damage, hole in ground
    "water_puddle",     # 5 - standing water, wet area
    "slippery_floor",   # 6 - ice, wet floor, slippery surface
    "clear_path"        # 7 - safe walking area (negative class)
]


def create_dataset_yaml(data_dir: Path) -> Path:
    """
    Create a dataset.yaml file for YOLO training.
    
    Expected structure:
    data/
      ├── images/
      │   ├── train/
      │   ├── val/
      │   └── test/
      └── labels/
          ├── train/
          ├── val/
          └── test/
    """
    dataset_yaml = {
        "path": str(data_dir.resolve()),
        "train": "images/train",
        "val": "images/val",
        "test": "images/test",
        "nc": len(CLASSES),
        "names": CLASSES
    }
    
    yaml_path = data_dir / "data.yaml"
    with open(yaml_path, 'w') as f:
        yaml.dump(dataset_yaml, f, default_flow_style=False)
    
    return yaml_path


def train_segmentation_model(
    data_yaml: Path,
    epochs: int = 100,
    batch_size: int = 16,
    imgsz: int = 320,
    resume: bool = False,
    device: str = "cpu",
) -> None:
    """
    Train YOLOv8 segmentation model.
    
    Args:
        data_yaml: Path to data.yaml with dataset config
        epochs: Number of training epochs
        batch_size: Batch size for training
        imgsz: Input image size
        resume: Resume from last checkpoint
        device: Device to train on (0 for GPU, cpu for CPU)
    """
    print(f"[train] Loading dataset configuration from {data_yaml}")
    
    if not data_yaml.exists():
        raise FileNotFoundError(
            f"Dataset YAML not found: {data_yaml}\n"
            "Run: python train_custom_segmentation.py --prepare-dirs"
        )
    
    print(f"[train] Training custom YOLOv8 segmentation model")
    print(f"[train] Classes: {', '.join(CLASSES)}")
    print(f"[train] Epochs: {epochs}, Batch Size: {batch_size}, Image Size: {imgsz}")
    
    # Load pretrained YOLOv8n segmentation model
    model = YOLO("yolov8n-seg.pt")
    
    # Train
    results = model.train(
        data=str(data_yaml),
        epochs=epochs,
        imgsz=imgsz,
        batch=batch_size,
        device=device,
        patience=15,  # Early stopping patience
        save=True,
        resume=resume,
        optimizer="SGD",
        lr0=0.01,
        lrf=0.01,
        momentum=0.937,
        weight_decay=0.0005,
        warmup_epochs=5,
        warmup_momentum=0.8,
        warmup_bias_lr=0.1,
        hsv_h=0.015,
        hsv_s=0.7,
        hsv_v=0.4,
        degrees=0.0,
        translate=0.1,
        scale=0.5,
        flipud=0.5,
        fliplr=0.5,
        mosaic=1.0,
        mixup=0.0,
        copy_paste=0.0,
        project="runs/segment",
        name="smartcane_custom",
        exist_ok=True,
    )
    
    print(f"\n[train] ✓ Training complete!")
    print(f"[train] Best model saved to: runs/segment/smartcane_custom/weights/best.pt")
    print(f"[train] Last model saved to: runs/segment/smartcane_custom/weights/last.pt")


def export_to_tflite(
    weights_path: Path,
    imgsz: int = 320,
    half: bool = False,
) -> None:
    """
    Export trained YOLO model to TFLite format.
    
    Args:
        weights_path: Path to best.pt or last.pt
        imgsz: Input image size
        half: Use float16 quantization
    """
    print(f"\n[export] Loading trained model from {weights_path}")
    model = YOLO(str(weights_path))
    
    print(f"[export] Exporting to TFLite (imgsz={imgsz}, half={half})")
    export_path = model.export(
        format="tflite",
        imgsz=imgsz,
        half=half,
        nms=False,
        simplify=True,
    )
    
    # Rename to expected Android filename
    final_name = f"smartcane_segmentation_{imgsz}_float{'16' if half else '32'}.tflite"
    final_path = Path(final_name)
    shutil.copy(export_path, final_path)
    
    print(f"[export] ✓ Exported to: {final_path.resolve()}")
    print(f"[export] Copy to Android assets:")
    print(f"  cp {final_path} android-app/app/src/main/assets/")


def prepare_directory_structure(data_dir: Path = Path("data")) -> None:
    """Create required directory structure for dataset."""
    dirs = [
        data_dir / "images" / "train",
        data_dir / "images" / "val",
        data_dir / "images" / "test",
        data_dir / "labels" / "train",
        data_dir / "labels" / "val",
        data_dir / "labels" / "test",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        print(f"Created: {d}")
    
    # Create README
    readme = data_dir / "README.md"
    readme.write_text(f"""# Smart Cane Custom Segmentation Dataset

## Classes
{chr(10).join(f"{i}: {cls}" for i, cls in enumerate(CLASSES))}

## Image Organization
- Place training images (80%) in: `images/train/`
- Place validation images (10%) in: `images/val/`
- Place test images (10%) in: `images/test/`

## Label Format
Each image needs a corresponding .txt file in the matching labels/ subdirectory.

Format (YOLO Segmentation):
```
<class_id> <x1> <y1> <x2> <y2> ... <xn> <yn>
```

Where:
- `class_id`: 0-{len(CLASSES)-1}
- `x1 y1 x2 y2 ...`: Normalized polygon coordinates (0-1, representing the segmentation mask)

Example:
```
0 0.5 0.2 0.8 0.2 0.8 0.6 0.5 0.6
```

## Tools for Creating Labels
- CVAT: https://cvat.org/
- Roboflow: https://roboflow.com/
- Label Studio: https://labelstud.io/
""")
    print(f"Created: {readme}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train custom YOLOv8 segmentation model for Smart Cane"
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help="Dataset directory (default: data/)"
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=100,
        help="Number of training epochs (default: 100)"
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=16,
        help="Batch size (default: 16)"
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=320,
        help="Input image size (default: 320)"
    )
    parser.add_argument(
        "--half",
        action="store_true",
        help="Use float16 quantization"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume training from last checkpoint"
    )
    parser.add_argument(
        "--device",
        default="cpu",
        help="Device: 0 for GPU, cpu for CPU (default: cpu)"
    )
    parser.add_argument(
        "--prepare-dirs",
        action="store_true",
        help="Prepare directory structure for dataset"
    )
    parser.add_argument(
        "--export-only",
        type=str,
        help="Export model from path to TFLite (skip training)"
    )
    
    args = parser.parse_args()
    data_dir = Path(args.data_dir)
    
    if args.prepare_dirs:
        print("[setup] Preparing directory structure...")
        prepare_directory_structure(data_dir)
        return
    
    if args.export_only:
        weights_path = Path(args.export_only)
        if not weights_path.exists():
            raise FileNotFoundError(f"Model not found: {weights_path}")
        export_to_tflite(weights_path, args.imgsz, args.half)
        return
    
    # Create data.yaml
    yaml_path = create_dataset_yaml(data_dir)
    
    # Train model
    train_segmentation_model(
        yaml_path,
        epochs=args.epochs,
        batch_size=args.batch,
        imgsz=args.imgsz,
        resume=args.resume,
        device=args.device,
    )
    
    # Export to TFLite
    best_weights = data_dir.parent / "runs" / "segment" / "smartcane_custom" / "weights" / "best.pt"
    if best_weights.exists():
        export_to_tflite(best_weights, args.imgsz, args.half)


if __name__ == "__main__":
    main()
