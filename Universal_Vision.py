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

 IP WEBCAM SETUP:
     1. Install "IP Webcam" app on Android phone
     2. Start the app and get the video URL
     3. Run: python Universal_Vision.py --src http://192.168.1.5:8080/video

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
import platform
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
    """Map YOLO class names to the labels the cane cares about.
    Custom segmentation classes are passed through so hazards like
    water puddle, slippery floor, and pothole become visible.
    """
    normalized = class_name.strip().lower()
    if normalized in {"car", "bus", "truck", "motorcycle"}:
        return "Vehicle"
    if normalized == "person":
        return "Person"
    if normalized == "bicycle":
        return "Bicycle"
    if normalized == "dog":
        return "Dog"
    if normalized in {"bench", "chair"}:
        return "Furniture"
    if normalized in {"traffic light", "stop sign"}:
        return "TrafficSign"
    if normalized in {"water puddle", "puddle"}:
        return "Water Puddle"
    if normalized in {"slippery floor", "slippery"}:
        return "Slippery Floor"
    if normalized == "pothole":
        return "Pothole"
    return class_name.title() if class_name else ""


def run(src: str, model_path: str, conf: float, show: bool) -> None:
    device = pick_device()
    print(f"[vision] device={device}  src={src}  model={model_path}", flush=True)
    
    # Detect if using IP Webcam
    is_ip_webcam = src.startswith("http://") or src.startswith("rtsp://")
    if is_ip_webcam:
        print(f"[vision] Connecting to IP Webcam: {src}", flush=True)
    elif platform.system() == "Darwin":
        print("[vision] Detected macOS - configuring camera access", flush=True)

    model = YOLO(model_path)

    def open_capture(source: str) -> cv2.VideoCapture:
        if source.isdigit():
            return cv2.VideoCapture(int(source))
        cap = cv2.VideoCapture(source)
        if not cap.isOpened() and source.startswith(("http://", "https://", "rtsp://")):
            try:
                cap.release()
            except Exception:
                pass
            cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG)
        return cap

    # Try to open camera with macOS-specific settings
    cap = open_capture(src)
    
    # Set for macOS: request proper camera backend
    if platform.system() == "Darwin" and src.isdigit():
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Reduce buffer on macOS
        cap.set(cv2.CAP_PROP_FPS, 30)
    
    if not cap.isOpened():
        print(f"[vision] ERROR: could not open stream {src}", file=sys.stderr)
        print(f"[vision] Platform: {platform.system()}", file=sys.stderr)
        if is_ip_webcam:
            print(f"[vision] Check IP Webcam app is running and URL is correct", file=sys.stderr)
            print(f"[vision] Make sure phone and computer are on same network", file=sys.stderr)
        else:
            print(f"[vision] Make sure camera has permissions on macOS: System Preferences > Security & Privacy > Camera", file=sys.stderr)
        sys.exit(1)

    # Verify camera is working
    ret, frame = cap.read()
    if not ret:
        print("[vision] ERROR: could not read from camera", file=sys.stderr)
        cap.release()
        sys.exit(1)
    print(f"[vision] Camera opened successfully - frame size: {frame.shape}", flush=True)
    if is_ip_webcam:
        print(f"[vision] IP Webcam stream active - ready for object detection", flush=True)

    # Open log file for writing (overwrite on each run to keep it small)
    log_file = open("vision.log", "w")

    try:
        last_print = 0.0
        frame_count = 0
        first_frame = True
        
        while True:
            if first_frame:
                # Use the frame we already read for verification
                first_frame = False
            else:
                ok, frame = cap.read()
                if not ok:
                    print("[vision] frame grab failed, retrying...", flush=True)
                    time.sleep(0.5)
                    continue

            frame_count += 1
            
            # YOLO inference
            results = model.predict(frame, device=device, conf=conf, verbose=False)
            r = results[0]

            # Collect labels this frame with distance estimation
            detections: list[tuple[str, float, float]] = []  # (label, confidence, distance_mm)
            for box in r.boxes:
                cls_id = int(box.cls[0])
                cls_name = model.names[cls_id]
                mapped = label_for(cls_name)
                if mapped:
                    # Estimate distance based on bounding box size
                    # Larger bounding box = closer object
                    x1, y1, x2, y2 = box.xyxy[0]
                    bbox_width = x2 - x1
                    bbox_height = y2 - y1
                    bbox_area = bbox_width * bbox_height
                    
                    # Simple distance estimation: larger area = closer distance
                    # Calibrated for typical smart cane use case
                    # Max distance we care about: ~3000mm (3m)
                    # Min distance: ~300mm (too close to be useful)
                    frame_area = frame.shape[0] * frame.shape[1]
                    area_ratio = bbox_area / frame_area
                    
                    # Distance estimation formula (empirical)
                    # area_ratio of 0.1 = ~500mm, area_ratio of 0.5 = ~200mm
                    if area_ratio > 0.6:  # Very close
                        distance_mm = 200
                    elif area_ratio > 0.3:  # Close
                        distance_mm = 500
                    elif area_ratio > 0.1:  # Medium
                        distance_mm = 1000
                    elif area_ratio > 0.05:  # Far
                        distance_mm = 1500
                    else:  # Very far
                        distance_mm = 2500
                    
                    detections.append((mapped, float(box.conf[0]), distance_mm))

            # Throttle console output to ~5 Hz so the dashboard parser isn't flooded
            now = time.time()
            if detections and now - last_print > 0.2:
                # Format: "VISION|Car:0.82:1200,Person:0.91:800" (label:conf:distance_mm)
                payload = ",".join(f"{name}:{conf:.2f}:{dist:.0f}" for name, conf, dist in detections)
                output_line = f"VISION|{payload}"
                print(output_line, flush=True)
                log_file.write(output_line + "\n")
                log_file.flush()
                last_print = now
            
            # Periodic status update every 100 frames
            if frame_count % 100 == 0:
                print(f"[vision] Status: {frame_count} frames processed", flush=True)

            # VIBECODER: push `detections` into a socket/queue for Module D here.

            if show:
                try:
                    annotated = r.plot()
                    # macOS-safe window display
                    cv2.imshow("Smart Cane Vision", annotated)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break
                except Exception as e:
                    print(f"[vision] Display warning (headless mode?): {e}", file=sys.stderr)
                    show = False  # Disable display for this session
    except KeyboardInterrupt:
        print("[vision] Interrupted by user", flush=True)
    except Exception as e:
        print(f"[vision] Error: {e}", file=sys.stderr)
    finally:
        cap.release()
        log_file.close()
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
