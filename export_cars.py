"""Export trained cars model to TFLite float16."""
from pathlib import Path
import shutil
from ultralytics import YOLO

pt = Path("runs/detect/cars/train/weights/best.pt")
print(f"Loading {pt}...")
model = YOLO(str(pt))
out = model.export(format="tflite", imgsz=320, half=True, int8=False, nms=False)
print(f"Exported to: {out}")

Path("models").mkdir(exist_ok=True)
candidates = list(Path(out).parent.glob("*.tflite")) if out else []
if not candidates:
    candidates = list(pt.parent.glob("*.tflite")) + list(pt.parent.glob("**/*.tflite"))

print(f"TFLite files found: {candidates}")
if candidates:
    dst = Path("models/cars_float16.tflite")
    shutil.copy2(str(candidates[0]), str(dst))
    print(f"Saved to: {dst.resolve()}")
else:
    print("ERROR: no .tflite found after export")
