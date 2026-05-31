# Smart Cane Clip-On — Project Report

**Project:** Smart Cane Clip-On — Assistive Navigation System for the Visually Impaired
**Repository:** SEM2EL
**Report Date:** May 2026
**Scope:** End-to-end design, methodology, tooling, and challenges across the hardware (ESP32 sensor cluster) and software (Android app, Python vision/dashboard, custom ML models) subsystems.

---

## 1. Executive Summary

The Smart Cane Clip-On is a modular assistive device that augments a traditional white cane with electronic obstacle perception, drop detection, fall alerting, and on-device computer vision. The system is composed of three loosely-coupled modules:

- **Module A — Sensor Cane (ESP32 firmware):** TF-Luna LiDAR + VL53L0X ToF + MPU6050 + LDR; emits sensor packets over USB serial or WiFi WebSocket.
- **Module B — Android Gateway:** Foreground service that receives ESP32 packets, raises SMS-based SOS on fall, and runs an on-device YOLOv8 TFLite pipeline (CameraX + TensorFlow Lite) for obstacle/pothole/electric-pole detection with TTS callouts.
- **Module C — Vision / Dashboard (Python):** Streamlit dashboard for live monitoring (Serial / WiFi / Mock modes); standalone `Universal_Vision.py` runs YOLOv8 on an IP-Webcam stream; training pipelines (`train_obstacle_models.py`, `train_custom_segmentation.py`) produce the TFLite models deployed to Android.

The system has been validated end-to-end: firmware builds and streams at 10 Hz, the Android app builds (`BUILD SUCCESSFUL`) and deploys with bundled `.tflite` assets, and three obstacle models (tree, electric pole, pothole) plus a generic COCO YOLOv8n model are bundled in `apk_current/assets/`.

---

## 2. System Architecture

```
┌─────────────────────┐        ┌──────────────────────────┐        ┌─────────────────────────┐
│  ESP32 Sensor Cane  │        │   Android Gateway App    │        │  Python Dashboard / ML  │
│  (Cane_Firmware*)   │        │   (com.smartcane.gateway)│        │  (Project_Dashboard.py) │
├─────────────────────┤        ├──────────────────────────┤        ├─────────────────────────┤
│ TF-Luna LiDAR (UART)│        │ CaneSosService (FG)      │        │ Streamlit UI            │
│ VL53L0X ToF (I2C)   │ Serial │  ├─ OkHttp WebSocket cli │  WiFi  │  ├─ SerialSource        │
│ MPU6050 (I2C)       │  ───►  │  ├─ Packet parser        │ ◄────► │  ├─ WiFiSource (WS)     │
│ LDR (ADC)           │  WiFi  │  ├─ FusedLocation/SMS    │        │  ├─ MockSource          │
│ LCD 16x2 (I2C)      │  ───►  │  └─ Fall → SOS SMS       │        │  └─ Charts + zones      │
│ LED + Buzzer        │        │ CaneVisionActivity       │        │ Universal_Vision.py     │
│ WebSocket :81 (WiFi)│        │  ├─ CameraX preview      │        │  └─ YOLOv8 on RTSP/HTTP │
└─────────────────────┘        │  ├─ TFLite (yolov8n_seg) │        │ Training pipelines      │
                               │  ├─ PotholeDetector      │        │  ├─ train_obstacle_…    │
                               │  ├─ ElectricPoleDetector │        │  ├─ train_custom_seg…   │
                               │  └─ TTS callouts         │        │  └─ export_yolo_*tflite │
                               │ PhoneDashboardActivity   │        └─────────────────────────┘
                               │  └─ live fused view + SOS│
                               └──────────────────────────┘
```

Data protocol (both serial and WebSocket payloads): `dist_fwd,dist_drop,fall_flag,light_val`, e.g. `045,180,0,0550` at ~10 Hz.

---

## 3. Hardware Subsystem

### 3.1 Bill of Materials

| Component | Role | Interface | Pin |
|---|---|---|---|
| ESP32 DevKit | MCU, WiFi, dual-core | — | — |
| TF-Luna LiDAR | Front-facing obstacle range (0.2–8 m) | UART2 @ 115200 | RX 16 / TX 17 |
| VL53L0X ToF | Downward drop/step detection (50–1200 mm) | I2C @ 0x29 | SDA 21 / SCL 22 |
| MPU6050 IMU | Fall detection (raw accel sum) | I2C @ 0x68 | SDA 21 / SCL 22 |
| LDR (analog) | Ambient light → auto LED | ADC | GPIO 34 |
| 16×2 LCD | On-cane status, IP address | I2C @ 0x27 | SDA 21 / SCL 22 |
| LED | Dark indicator | GPIO output | GPIO 2 |
| Active buzzer | Proximity / fall alert | GPIO output | GPIO 4 |

### 3.2 Firmware Methodology

Two firmware variants are maintained:

- [Cane_Firmware.ino](Cane_Firmware.ino) — USB serial baseline; `L:<cm>,T:<mm>,LDR:<val>,F:<0|1>` at 10 Hz on Serial @ 115200.
- [Cane_Firmware_WiFi.ino](Cane_Firmware_WiFi.ino) — Adds `WiFi.h` + `WebSocketsServer` on port 81, broadcasts the same packet to all connected clients, prints assigned IP to LCD and Serial. Marked `v2.1 NON-BLOCKING BUILD` — the WiFi connect loop yields so sensor reads are not starved.

Key design choices:

1. **Non-blocking main loop.** A single `LOOP_MS = 50` cadence drives all sensors; WiFi reconnect, buzzer toggling, and LCD IP refresh are time-gated via `millis()` checkpoints (`lastTick`, `lastWifiRetry`, `lastBuzzerOff`, `lastIPDisplay`) so a slow sensor cannot stall the loop.
2. **Tiered buzzer logic.** Distance bands map to beep intervals (150 / 400 / 800 ms) with fall detection overriding to a continuous tone — safety-critical signals always win.
3. **Library-free MPU6050.** Direct `Wire` register access (`PWR_MGMT_1 = 0x6B`, `ACCEL_XOUT_H = 0x3B`) avoids dependency on the conflicting Adafruit/Electronic Cats MPU libraries.
4. **Manual TF-Luna framing.** The 9-byte `0x59 0x59 …` frame is parsed inline rather than via a vendor library, keeping the build portable across ESP32 board package versions.
5. **Configurable thresholds** at the top of each firmware file: `LDR_DARK_THRESHOLD = 700`, `FALL_THRESHOLD = 20000` (raw accel sum). Documented in [FIRMWARE_SETUP.md](FIRMWARE_SETUP.md).

### 3.3 Hardware Challenges Faced

| Challenge | Resolution |
|---|---|
| **I2C bus contention** between VL53L0X (0x29), MPU6050 (0x68), and LCD (0x27) | Verified non-overlapping addresses; shared SDA/SCL on GPIO 21/22 with pull-ups on long wires. |
| **TF-Luna intermittent frame drops** when MCU was busy | Switched to inline 9-byte framing inside `loop()` and increased read window (`while … available() >= 9`). |
| **MPU6050 library conflicts** with the ESP32 core | Replaced library calls with raw register reads via `Wire`. |
| **WiFi connect blocking the sensor loop** | Connect attempt time-boxed in `setup()`; runtime reconnects are non-blocking via `lastWifiRetry` gate. |
| **5 GHz incompatibility** of ESP32 | Documented explicitly in [ESP32_WIFI_CONNECTION_GUIDE.md](ESP32_WIFI_CONNECTION_GUIDE.md) — only 2.4 GHz SSIDs are accepted. |
| **False fall triggers** from sharp arm movement | Raw accel sum threshold (`20000`) tuned empirically; fall flag re-armed only when accel returns to baseline. |
| **CH340/CP2102 USB driver missing on Windows** | Captured in firmware setup docs with driver links. |

---

## 4. Software Subsystem

### 4.1 Android Gateway App

**Package:** `com.smartcane.gateway` · **Min SDK:** 26 · **Build:** Gradle Kotlin DSL

Source files under [android-app/app/src/main/java/com/smartcane/gateway](android-app/app/src/main/java/com/smartcane/gateway):

| File | Responsibility |
|---|---|
| [MainActivity.kt](android-app/app/src/main/java/com/smartcane/gateway/MainActivity.kt) | Runtime permission orchestration (BLUETOOTH_*, FINE_LOCATION, SEND_SMS, CAMERA, POST_NOTIFICATIONS), service bootstrap, auto-launches vision activity. |
| [Android_SOS_Service.kt](android-app/app/src/main/java/com/smartcane/gateway/Android_SOS_Service.kt) | Foreground `CaneSosService`: OkHttp `WebSocket` to ESP32, packet parser, FusedLocation, `SmsManager` SOS with 60 s cooldown, LocalBroadcast `ACTION_SENSOR_DATA`. |
| [CaneVisionActivity.kt](android-app/app/src/main/java/com/smartcane/gateway/CaneVisionActivity.kt) | CameraX preview + `ImageAnalysis` → TFLite inference → overlay + TTS (3 s per-label cooldown). |
| [TfliteObjectDetector.kt](android-app/app/src/main/java/com/smartcane/gateway/TfliteObjectDetector.kt) | Loads first valid YOLOv8 TFLite asset, autodetects detect-vs-seg (84 vs 116 channels) and custom-vs-COCO (8 vs 80 classes), per-class confidence thresholds, NMS. |
| [PotholeDetector.kt](android-app/app/src/main/java/com/smartcane/gateway/PotholeDetector.kt) | Dedicated `pothole_detector_320_float16.tflite` head (8-class road-defect model). |
| [ElectricPoleDetector.kt](android-app/app/src/main/java/com/smartcane/gateway/ElectricPoleDetector.kt) | Dedicated electric-pole TFLite head. |
| [PhoneDashboardActivity.kt](android-app/app/src/main/java/com/smartcane/gateway/PhoneDashboardActivity.kt) | Programmatic UI showing live ESP32 packets + vision results; fuses both LocalBroadcast feeds. |
| [SosContactsActivity.kt](android-app/app/src/main/java/com/smartcane/gateway/SosContactsActivity.kt) | Emergency contact CRUD persisted in SharedPreferences. |
| [NavigationActivity.kt](android-app/app/src/main/java/com/smartcane/gateway/NavigationActivity.kt) | Maps/intent-based navigation hand-off. |
| [FallTriggerTest.kt](android-app/app/src/main/java/com/smartcane/gateway/FallTriggerTest.kt) | Manual fall trigger for SMS pipeline verification. |

**Methodology highlights:**

- **Foreground service + LocalBroadcastManager** decouples networking (`CaneSosService`) from UI (`PhoneDashboardActivity`), so the SOS pipeline keeps running with the screen off.
- **Defensive model loader.** `TfliteObjectDetector.loadModel()` iterates a `MODEL_CANDIDATES` list (`smartcane_segmentation_320_float16` → `yolov8n_seg_320_float16` → `yolov8n_320_float16` → …), skipping any stub file under 1 KB. This makes the APK robust to missing or partial assets.
- **GPU delegate with CPU fallback.** Each detector tries `GpuDelegate()` inside `runCatching` and falls back to 4 CPU threads on unsupported devices.
- **Per-class confidence thresholds** (safety-first): person/vehicle = 0.25–0.30 (aggressive), furniture/animal = 0.35 (medium), hazards like puddle/slippery = 0.50 (conservative), `clear_path` = 0.60 (very conservative to suppress false reassurance).
- **TTS rate-limit.** `ALERT_COOLDOWN_MS = 3000` per label prevents speech spamming when the same obstacle stays in frame.

### 4.2 Python Dashboard & Vision

| File | Purpose |
|---|---|
| [Project_Dashboard.py](Project_Dashboard.py) | Streamlit dashboard with `SerialSource`, `WiFiSource` (WebSocket client), `MockSource`; renders zone bands (CLEAR / CAUTION / WARNING / CRITICAL) and trend charts. |
| [Universal_Vision.py](Universal_Vision.py) | Standalone YOLOv8 runner against IP Webcam / RTSP / local webcam, emits `VISION|label:conf,…` lines for the dashboard to tail. |
| [train_obstacle_models.py](train_obstacle_models.py) | Trains three independent YOLOv8n detectors (tree, electric_pole, steps_kerb) and exports each to 320 px float16 TFLite. |
| [train_custom_segmentation.py](train_custom_segmentation.py) | YOLOv8 segmentation pipeline for the 8-class Smart-Cane taxonomy. |
| [export_yolo_tflite.py](export_yolo_tflite.py), [export_yolo_seg_tflite.py](export_yolo_seg_tflite.py) | Stand-alone TFLite exporters with float16 quantization. |
| [prepare_pothole_dataset.py](prepare_pothole_dataset.py), [prepare_unified_dataset.py](prepare_unified_dataset.py) | Roboflow → YOLO conversion + absolute-path `data.yaml` rewrites. |
| [generate_sample_dataset.py](generate_sample_dataset.py) | Synthetic dataset generator so the pipeline can be smoke-tested without real annotations. |

**Methodology highlights:**

- **Three connection modes** in the dashboard sidebar — Serial / WiFi / Mock — share a single `Packet` parser, so the same downstream charting code works regardless of transport.
- **Auto-reconnect WebSocket client** (`WiFiSource`) caches the connection across Streamlit reruns; timeouts and dead sockets are caught silently to keep the UI responsive.
- **Mode-aware status banner** (🎮 Mock / 📡 WiFi LIVE / 🔌 Serial LIVE) prevents the user from misreading mock data as real telemetry.

### 4.3 Custom ML Models

8-class Smart Cane taxonomy:

| ID | Class | Threshold | Rationale |
|---|---|---|---|
| 0 | person | 0.35 | aggressive — safety |
| 1 | furniture | 0.40 | medium |
| 2 | vehicle | 0.35 | aggressive — safety |
| 3 | animal | 0.40 | medium |
| 4 | pothole | 0.45 | medium-high |
| 5 | water puddle | 0.50 | conservative |
| 6 | slippery floor | 0.50 | conservative |
| 7 | clear path | 0.60 | very conservative — avoid false reassurance |

**Pipeline:** image collection → Roboflow/CVAT/Label Studio annotation → YOLO segmentation dataset.yaml → YOLOv8n training (320 px, float16) → TFLite export → copy to `android-app/app/src/main/assets/` → `./gradlew assembleDebug`.

**Performance budget:** 6.6 MB float16 TFLite, ~200–300 ms per frame on mid-range Android, 320×320 input.

Models currently shipped in [apk_current/assets](apk_current/assets):

- `yolov8n_320_float16.tflite` — generic COCO baseline
- `yolov8n_seg_320_float16.tflite` — segmentation baseline
- `pothole_detector_320_float16.tflite` — single-class pothole
- `smartcane_unified_320_float16.tflite` — unified 8-class detector

### 4.4 Software Challenges Faced

| Challenge | Resolution |
|---|---|
| **TFLite tensor shape varied** between detect (`[1,84,2100]`) and seg (`[1,116,2100]`) and between COCO (80) and custom (8) | Single loader in `TfliteObjectDetector` inspects output shape at init and branches into the right post-processing + label map. |
| **Stub `.tflite` assets** (29-byte placeholders from earlier commits) were being loaded and crashing inference | `MODEL_CANDIDATES` ordering + `declaredLength < 1024` skip guard. |
| **GPU delegate failures** on devices without OpenGL ES 3.1 | `runCatching { GpuDelegate() }` with 4-thread CPU fallback. |
| **TTS spamming** the same label every frame | Per-label `ALERT_COOLDOWN_MS = 3000` map. |
| **SMS spamming** on continuous fall flag | 60 s `SMS_COOLDOWN_MS` rate-limit inside `CaneSosService`. |
| **Permission matrix** churn across API 26–34 (BLE runtime perms in 31+, POST_NOTIFICATIONS in 33+) | Conditional `buildList` per API level in `MainActivity` + `PhoneDashboardActivity`. |
| **Streamlit reruns** killing WebSocket connections | Connection caching keyed by `(mode, ip)` so reruns reuse the same socket. |
| **Roboflow `data.yaml` uses `../train/images`** which breaks when training from a different cwd | `fix_data_yaml()` rewrites to absolute paths and emits `data_abs.yaml`. |
| **No labeled data for the 8-class taxonomy** initially | `generate_sample_dataset.py` produces synthetic masks so the training + export + Android deploy pipeline can be validated end-to-end before real annotation begins. |
| **Phase 2 WiFi rollout** had to avoid destabilizing the working serial mode | Branched as `phase-2-changes` with `WiFiSource` added alongside (not replacing) `SerialSource`; old serial path is byte-identical. |
| **APK ships multiple model assets** (large APK) | float16 quantization at 320 px keeps each model ≈6 MB; only models actively loaded are mmapped. |

---

## 5. Tooling Inventory

**Hardware / Firmware**

- Arduino IDE (ESP32 board package by Espressif)
- Libraries: `Adafruit_VL53L0X`, `LiquidCrystal_I2C`, `WebSocketsServer` (Markus Sattler), built-in `Wire`, `WiFi`, `HardwareSerial`
- TF-Luna, VL53L0X, MPU6050, LDR, 16×2 I2C LCD, ESP32 DevKit

**Android**

- Android Studio + Gradle Kotlin DSL (`android-app/`)
- AndroidX: AppCompat, CameraX (`camera-camera2`, `camera-lifecycle`, `camera-view` 1.3.4), LocalBroadcastManager, FusedLocation
- TensorFlow Lite 2.14.0 (`tflite`, `tflite-support` 0.4.4, `tflite-gpu`)
- OkHttp WebSocket client, Kotlin Coroutines
- Android `SmsManager`, `TextToSpeech`, `ToneGenerator`, `Vibrator`

**Python (training, vision, dashboard)**

- Python 3.9–3.12, `.venv` virtual environment
- Ultralytics YOLOv8 (`ultralytics`), PyTorch (`torch`), OpenCV (`opencv-python`)
- TensorFlow + `onnx` for TFLite export
- Streamlit, pandas, numpy, pyserial, websocket-client (`requirements.txt`)
- Dataset tooling: Roboflow, CVAT (Docker), Label Studio

**Dev workflow**

- Git with feature branches (`main`, `phase-2-changes`, custom-model branches) — see [GIT_WORKFLOW.md](GIT_WORKFLOW.md)
- Helper scripts: [setup_custom_model.sh](setup_custom_model.sh), [CHECKLIST.sh](CHECKLIST.sh), [QUICK_REFERENCE.sh](QUICK_REFERENCE.sh)
- ADB for install + `logcat | grep smartcane` for runtime diagnostics

---

## 6. Methodology Summary

**Hardware methodology** — sensor-fusion-first design: each sensor owns a single failure mode (LiDAR = forward range, ToF = drop, IMU = fall, LDR = light). The firmware is intentionally library-light (raw I2C registers, manual TF-Luna framing) to maximize portability across ESP32 core versions, and the main loop is non-blocking so a single slow sensor cannot starve the others. The serial protocol is a fixed-width CSV that doubles as the WebSocket payload so the same parser is used by every consumer (laptop dashboard, Android service, mock generator).

**Software methodology** — three-tier separation:

1. **Transport** (`SerialSource` / `WiFiSource` / `MockSource` in Python; `CaneSosService` WebSocket client in Kotlin) — pluggable, swappable at runtime.
2. **Perception** (TFLite models with auto-detected shape and class count, per-class thresholds, NMS, GPU-with-CPU-fallback) — multiple specialized detectors run cooperatively (`TfliteObjectDetector` + `PotholeDetector` + `ElectricPoleDetector`) instead of one monolithic model.
3. **Action** (TTS callouts, buzzer beep tiers, SMS SOS with cooldown, dashboard zone banners) — every output channel is rate-limited so the user is never overwhelmed and the SMS gateway is never abused.

ML development follows a *validate-pipeline-then-collect-data* approach: synthetic data (`generate_sample_dataset.py`) is used to prove that training → TFLite export → Android deployment works end-to-end before investing weeks in real annotation. Models are exported at 320×320 float16 to fit the mobile inference budget (~200–300 ms/frame) while keeping the APK shippable.

---

## 7. Current Status

- ESP32 firmware (serial + WiFi) compiles and streams at 10 Hz.
- Android app builds clean (`BUILD SUCCESSFUL`) and bundles four TFLite models in `apk_current/assets/`.
- Python dashboard supports Serial / WiFi / Mock; vision module runs against IP Webcam streams.
- Three training pipelines are in place (tree, electric pole, custom 8-class segmentation); the electric-pole model has completed a 50-epoch run (`runs/detect/electric_pole`, `models/electric_pole_float16.tflite`).
- Outstanding work: collect production annotated data for the 8-class taxonomy, retrain with `--epochs 100+` on GPU, and field-test fall-trigger thresholds with real users.

---

## 8. Reference Documents in Repository

- [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) — custom-model implementation notes
- [PHASE2_CHANGES_SUMMARY.md](PHASE2_CHANGES_SUMMARY.md) — WiFi rollout changeset
- [CUSTOM_MODEL_README.md](CUSTOM_MODEL_README.md), [CUSTOM_MODEL_TRAINING.md](CUSTOM_MODEL_TRAINING.md) — ML training guides
- [FIRMWARE_SETUP.md](FIRMWARE_SETUP.md) — full hardware/firmware setup
- [ESP32_WIFI_CONNECTION_GUIDE.md](ESP32_WIFI_CONNECTION_GUIDE.md) — WiFi onboarding walkthrough
- [IP_WEBCAM_README.md](IP_WEBCAM_README.md) — vision-via-phone-camera setup
- [GIT_WORKFLOW.md](GIT_WORKFLOW.md), [QUICK_REFERENCE.md](QUICK_REFERENCE.md), [PULL_REQUEST.md](PULL_REQUEST.md) — process docs
