#!/usr/bin/env bash

# Smart Cane Custom Model - Quick Reference Card
# Copy and paste commands below for quick execution

# ==============================================================================
# PHASE 1: TEST WITH SAMPLE DATA (5-15 minutes)
# ==============================================================================

# 1. Generate synthetic dataset (no real data needed)
python generate_sample_dataset.py --images 100

# 2. Train on sample data (CPU ~10 min, GPU ~2 min)
python train_custom_segmentation.py --epochs 30 --batch 8 --device cpu

# 3. Export to TFLite
python train_custom_segmentation.py --export-only runs/segment/smartcane_custom/weights/best.pt --half

# 4. Copy model to Android
cp smartcane_segmentation_320_float16.tflite android-app/app/src/main/assets/

# 5. Build and test Android app
cd android-app
./gradlew assembleDebug
# Then install: adb install -r app/build/outputs/apk/debug/app-debug.apk

# ==============================================================================
# PHASE 2: COLLECT REAL DATA (1-2 weeks)
# ==============================================================================

# Option A: CVAT (Professional annotation tool)
docker run -d -p 8080:8080 cvat/cvat:latest
# Open http://localhost:8080
# Create → Upload images → Annotate → Export as YOLO Segmentation

# Option B: Roboflow (Easiest, Recommended)
# 1. Sign up: https://roboflow.com/
# 2. Create instance segmentation project
# 3. Upload 300+ images
# 4. Annotate in web UI
# 5. Export as "YOLO Segmentation"

# Option C: Label Studio
pip install label-studio
label-studio start
# Open http://localhost:8080
# Create segmentation project → Annotate → Export

# Directory structure after annotation:
# data/
# ├── images/
# │   ├── train/     (250 images, 80%)
# │   ├── val/       (30 images, 10%)
# │   └── test/      (30 images, 10%)
# └── labels/        (YOLO format .txt files)

# ==============================================================================
# PHASE 3: TRAIN CUSTOM MODEL (1-4 hours depending on GPU)
# ==============================================================================

# Basic training (CPU - slow but works)
python train_custom_segmentation.py \
    --data-dir data \
    --epochs 50 \
    --batch 8 \
    --device cpu

# Production training (GPU - recommended)
python train_custom_segmentation.py \
    --data-dir data \
    --epochs 100 \
    --batch 32 \
    --device 0 \
    --patience 20

# Resume training if interrupted
python train_custom_segmentation.py \
    --data-dir data \
    --epochs 150 \
    --resume

# Advanced tuning (better accuracy, slower)
python train_custom_segmentation.py \
    --data-dir data \
    --epochs 200 \
    --batch 32 \
    --imgsz 640 \
    --device 0 \
    --lr0 0.01 \
    --warmup-epochs 5

# ==============================================================================
# PHASE 4: VALIDATE AND EXPORT (30 minutes)
# ==============================================================================

# Check training results
cat runs/segment/smartcane_custom/results.csv

# Export best model to TFLite (float16 for mobile)
python train_custom_segmentation.py \
    --export-only runs/segment/smartcane_custom/weights/best.pt \
    --imgsz 320 \
    --half

# ==============================================================================
# PHASE 5: DEPLOY TO ANDROID (30 minutes)
# ==============================================================================

# Copy model to assets (exact filename matters!)
cp smartcane_segmentation_320_float16.tflite \
   android-app/app/src/main/assets/yolov8n_seg_320_float16.tflite

# Or if you want to rename:
mv smartcane_segmentation_320_float16.tflite \
   android-app/app/src/main/assets/yolov8n_seg_320_float16.tflite

# Build Android app
cd android-app
./gradlew clean
./gradlew assembleDebug

# Install on connected device
adb install -r app/build/outputs/apk/debug/app-debug.apk

# Run the app
adb shell am start -n com.smartcane.gateway/.MainActivity

# View logs (optional)
adb logcat | grep smartcane

# ==============================================================================
# TROUBLESHOOTING COMMANDS
# ==============================================================================

# Check if Python dependencies installed
pip list | grep -E "ultralytics|tensorflow|opencv"

# Check if model file exists
ls -lh android-app/app/src/main/assets/*.tflite

# Verify Android build
cd android-app && ./gradlew clean assemble Debug --stacktrace

# View Android logcat for errors
adb logcat -s SmartCane

# Check trained model metrics
python -c "
import pandas as pd
df = pd.read_csv('runs/segment/smartcane_custom/results.csv')
print(df[['epoch', 'metrics/mAP50', 'val/box_loss', 'val/seg_loss']].tail())
"

# ==============================================================================
# DATASET STRUCTURE VERIFICATION
# ==============================================================================

# Check image count per split
echo "Training images:"
ls data/images/train/ | wc -l
echo "Validation images:"
ls data/images/val/ | wc -l
echo "Test images:"
ls data/images/test/ | wc -l

# Verify label files exist for each image
for img in data/images/train/*.jpg; do
    label="${img/images/labels}"
    label="${label/.jpg/.txt}"
    [ ! -f "$label" ] && echo "Missing: $label"
done

# Check label format (should be: class_id x1 y1 x2 y2 ...)
head -5 data/labels/train/*.txt

# ==============================================================================
# PERFORMANCE MONITORING
# ==============================================================================

# Monitor training in real-time (requires tensorboard)
pip install tensorboard
tensorboard --logdir runs/segment

# Check GPU usage during training (Unix/Linux)
watch -n 1 nvidia-smi

# Check memory usage
df -h
free -h

# ==============================================================================
# GIT COMMANDS
# ==============================================================================

# Pull latest custom model changes
git pull origin phase-2-changes

# Or fetch and checkout
git fetch origin
git checkout phase-2-changes

# View recent commits
git log --oneline -10

# Create new branch for your work
git checkout -b feature/custom-model-improvements

# Commit your changes
git add .
git commit -m "Improve custom model with [details]"
git push origin feature/custom-model-improvements

# ==============================================================================
# DOCUMENTATION LINKS
# ==============================================================================

# CUSTOM_MODEL_README.md          - 5-minute quick start
# CUSTOM_MODEL_TRAINING.md        - Complete 7-step guide
# IMPLEMENTATION_SUMMARY.md       - Status and timeline
# PULL_REQUEST.md                 - What changed and why
# This file (QUICK_REFERENCE.sh)  - All commands in one place

# ==============================================================================
# NEXT STEPS CHECKLIST
# ==============================================================================

# [ ] Test pipeline with sample data (Phase 1)
# [ ] Collect 300+ real images (Phase 2)
# [ ] Annotate with segmentation masks (Phase 2)
# [ ] Train custom model (Phase 3)
# [ ] Validate accuracy ≥ 85% (Phase 4)
# [ ] Deploy to Android (Phase 5)
# [ ] Field test in real environments (Phase 5)

# ==============================================================================
