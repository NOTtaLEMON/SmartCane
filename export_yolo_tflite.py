"""
============================================================================
 SMART CANE CLIP-ON  |  YOLOv8 → TFLite Export Utility
============================================================================
 Converts yolov8n.pt to a TFLite model optimised for on-device Android
 inference.  Run this ONCE on the laptop, then copy the output file into
 the Android project's assets folder.

 OUTPUT
 ------
 yolov8n_320_float16.tflite   (≈ 3.4 MB, fast enough for mid-range phones)

 ANDROID ASSET PATH
 ------------------
 Copy the .tflite file to:
   app/src/main/assets/yolov8n_320_float16.tflite

 USAGE
 -----
   python export_yolo_tflite.py
   python export_yolo_tflite.py --imgsz 320 --half    # default
   python export_yolo_tflite.py --imgsz 640 --half    # larger / slower
   python export_yolo_tflite.py --imgsz 320           # float32 (bigger)

 REQUIREMENTS
 ------------
   pip install ultralytics
============================================================================
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from ultralytics import YOLO


def main() -> None:
    parser = argparse.ArgumentParser(description="Export YOLOv8 to TFLite for Android")
    parser.add_argument("--model",  default="yolov8n.pt", help="Source .pt model")
    parser.add_argument("--imgsz",  type=int, default=320, help="Input image size (square)")
    parser.add_argument("--half",   action="store_true",   help="Float16 quantisation (recommended)")
    args = parser.parse_args()

    model_path = Path(args.model)
    if not model_path.exists():
        raise FileNotFoundError(f"Model not found: {model_path.resolve()}")

    print(f"[export] Loading {model_path} ...")
    model = YOLO(str(model_path))

    print(f"[export] Exporting → TFLite  imgsz={args.imgsz}  half={args.half}")
    # ultralytics writes the file next to the source model
    export_path = model.export(
        format="tflite",
        imgsz=args.imgsz,
        half=args.half,
        nms=False,          # we do NMS on-device in Kotlin for control
        simplify=True,
    )
    print(f"[export] Raw output → {export_path}")

    # Rename to a predictable filename so the Kotlin code can reference it
    suffix     = "_float16" if args.half else "_float32"
    final_name = f"yolov8n_{args.imgsz}{suffix}.tflite"
    final_path = Path(final_name)

    shutil.copy(export_path, final_path)
    print(f"\n[export] ✓  Saved as: {final_path.resolve()}")
    print()
    print("Next steps:")
    print(f"  1. Copy  {final_name}  into your Android project at:")
    print("     app/src/main/assets/yolov8n_320_float16.tflite")
    print("  2. Build & run the Android app — CaneVisionActivity will load it automatically.")


if __name__ == "__main__":
    main()
