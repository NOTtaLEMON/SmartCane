"""
============================================================================
 SMART CANE CLIP-ON  |  YOLOv8 → TFLite Export Utility
============================================================================
 Exports a YOLOv8 segmentation model to TFLite for on-device Android
 inference.  Run this ONCE on the laptop (needs Python ≤ 3.12), then
 copy the output file into the Android project's assets folder.

 OUTPUT
 ------
 yolov8n_seg_320_float16.tflite   (segmentation — preferred by the app)
 yolov8n_320_float16.tflite       (detection fallback, use --det flag)

 ANDROID ASSET PATH
 ------------------
 Copy the .tflite file to:
   android-app/app/src/main/assets/

 USAGE
 -----
   python export_yolo_tflite.py                  # seg model, 320, float16
   python export_yolo_tflite.py --imgsz 640      # larger / slower
   python export_yolo_tflite.py --det            # detection model instead
   python export_yolo_tflite.py --model custom.pt  # custom weights

 REQUIREMENTS (Python ≤ 3.12 only — TensorFlow not yet on 3.13/3.14)
 ------------
   pip install ultralytics tensorflow
============================================================================
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from ultralytics import YOLO


def main() -> None:
    parser = argparse.ArgumentParser(description="Export YOLOv8 to TFLite for Android")
    parser.add_argument("--model",  default=None,  help="Override source .pt model path")
    parser.add_argument("--imgsz",  type=int, default=320, help="Input image size (square)")
    parser.add_argument("--half",   action="store_true", default=True, help="Float16 (default on)")
    parser.add_argument("--no-half", dest="half", action="store_false", help="Use float32 instead")
    parser.add_argument("--det",    action="store_true", help="Export detection model instead of segmentation")
    args = parser.parse_args()

    # Pick default model: segmentation unless --det or --model is specified
    if args.model:
        model_path = Path(args.model)
    elif args.det:
        model_path = Path("yolov8n.pt")
    else:
        model_path = Path("yolov8n-seg.pt")   # auto-downloaded by ultralytics if missing

    if not model_path.exists():
        print(f"[export] Model {model_path} not found locally, downloading...")
    else:
        print(f"[export] Loading {model_path} ...")
    model = YOLO(str(model_path))

    is_seg = "seg" in model_path.stem
    print(f"[export] Exporting → TFLite  type={'seg' if is_seg else 'det'}  imgsz={args.imgsz}  half={args.half}")

    export_path = model.export(
        format="tflite",
        imgsz=args.imgsz,
        half=args.half,
        nms=False,
        simplify=True,
    )
    print(f"[export] Raw output → {export_path}")

    suffix     = "_float16" if args.half else "_float32"
    model_tag  = "yolov8n_seg" if is_seg else "yolov8n"
    final_name = f"{model_tag}_{args.imgsz}{suffix}.tflite"
    final_path = Path(final_name)

    shutil.copy(export_path, final_path)

    assets_path = Path("android-app/app/src/main/assets") / final_name
    shutil.copy(export_path, assets_path)

    print(f"\n[export] ✓  Saved as: {final_path.resolve()}")
    print(f"[export] ✓  Copied to assets: {assets_path.resolve()}")
    print()
    print("Next step: rebuild the Android app — CaneVisionActivity loads it automatically.")


if __name__ == "__main__":
    main()
