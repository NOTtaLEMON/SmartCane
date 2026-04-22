"""
============================================================================
 SMART CANE CLIP-ON  |  MODULE C: VISION INTELLIGENCE ("Eyes")
============================================================================
 Tech      : Python 3.9+  (Windows / Linux / Raspberry Pi)
 Framework : ultralytics YOLOv8
 Input     : RTSP or HTTP stream from a phone IP-camera app
             (e.g. "IP Webcam" on Android -> http://<phone-ip>:8080/video)
 Output    : Prints detected objects of interest to the console so Module D
             (Dashboard) can pick them up via stdout / file / socket.

 INSTALL:
     pip install ultralytics opencv-python

 RUN:
     python Universal_Vision.py --src http://192.168.1.5:8080/video
     python Universal_Vision.py --src rtsp://user:pass@cam/stream
     python Universal_Vision.py --src 0          # local webcam for testing

 CONSTRAINT: No MPS (macOS). Only CPU / CUDA auto-detect.
============================================================================
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2
import torch
from ultralytics import YOLO

# --- Classes we care about for a visually-impaired user --------------------
TARGET_CLASSES = {"car", "person", "bicycle", "motorcycle", "bus", "truck",
                  "dog", "bench", "chair", "traffic light", "stop sign"}

# Generic label used by the dashboard whenever something unknown but close
# is detected. VIBECODER: tweak the mapping in `label_for()` below.
GENERIC_OBSTACLE = "obstacle"


def pick_device() -> str:
    """CPU / CUDA only. Explicitly avoid MPS per project constraint."""
    return "cuda" if torch.cuda.is_available() else "cpu"


def label_for(class_name: str) -> str:
    """Map YOLO's 80 COCO classes -> the 3 semantic buckets the cane cares about."""
    if class_name in {"car", "bus", "truck", "motorcycle"}:
        return "Car"
    if class_name == "person":
        return "Person"
    if class_name in TARGET_CLASSES:
        return GENERIC_OBSTACLE
    return ""  # ignored


def run(src: str, model_path: str, conf: float, show: bool) -> None:
    device = pick_device()
    print(f"[vision] device={device}  src={src}  model={model_path}", flush=True)

    model = YOLO(model_path)

    cap = cv2.VideoCapture(src if not src.isdigit() else int(src))
    if not cap.isOpened():
        print(f"[vision] ERROR: could not open stream {src}", file=sys.stderr)
        sys.exit(1)

    last_print = 0.0
    while True:
        ok, frame = cap.read()
        if not ok:
            print("[vision] frame grab failed, retrying...", flush=True)
            time.sleep(0.5)
            continue

        # YOLO inference
        results = model.predict(frame, device=device, conf=conf, verbose=False)
        r = results[0]

        # Collect labels this frame
        detections: list[tuple[str, float]] = []
        for box in r.boxes:
            cls_id = int(box.cls[0])
            cls_name = model.names[cls_id]
            mapped = label_for(cls_name)
            if mapped:
                detections.append((mapped, float(box.conf[0])))

        # Throttle console output to ~5 Hz so the dashboard parser isn't flooded
        now = time.time()
        if detections and now - last_print > 0.2:
            # Format: "VISION|Car:0.82,Person:0.91"
            payload = ",".join(f"{name}:{conf:.2f}" for name, conf in detections)
            print(f"VISION|{payload}", flush=True)
            last_print = now

        # VIBECODER: push `detections` into a socket/queue for Module D here.

        if show:
            annotated = r.plot()
            cv2.imshow("Smart Cane Vision", annotated)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    cap.release()
    if show:
        cv2.destroyAllWindows()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="0",
                    help="RTSP/HTTP URL or webcam index (default: 0)")
    ap.add_argument("--model", default="yolov8n.pt",
                    help="YOLOv8 weights (n/s/m/l/x). Will auto-download.")
    ap.add_argument("--conf", type=float, default=0.45,
                    help="Confidence threshold")
    ap.add_argument("--show", action="store_true",
                    help="Display annotated window (disable for headless Pi)")
    args = ap.parse_args()

    run(args.src, args.model, args.conf, args.show)


if __name__ == "__main__":
    main()
