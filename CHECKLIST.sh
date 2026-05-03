#!/usr/bin/env bash

# Smart Cane YOLOv8 Custom Model - Implementation Checklist
# Track progress through all phases

cat << 'EOF'
╔═══════════════════════════════════════════════════════════════════════════╗
║  SMART CANE CUSTOM YOLOV8 SEGMENTATION - IMPLEMENTATION CHECKLIST        ║
╚═══════════════════════════════════════════════════════════════════════════╝

## PHASE 1: QUICK TEST (No Real Data Needed) - ~15 min
═══════════════════════════════════════════════════════════════════════════

[ ] 1.1 - Install dependencies
         python -m pip install ultralytics opencv-python tensorflow pyyaml

[ ] 1.2 - Generate synthetic dataset
         python generate_sample_dataset.py --images 100

[ ] 1.3 - Verify generated data structure
         ls -la data/images/train/ data/labels/train/

[ ] 1.4 - Train on sample data (CPU ~10 min)
         python train_custom_segmentation.py --epochs 30 --batch 8 --device cpu

[ ] 1.5 - Check training output
         ls -la runs/segment/smartcane_custom/weights/
         tail runs/segment/smartcane_custom/results.csv

[ ] 1.6 - Export to TFLite
         python train_custom_segmentation.py \
             --export-only runs/segment/smartcane_custom/weights/best.pt --half

[ ] 1.7 - Verify model file created (should be ~6.6 MB)
         ls -lh smartcane_segmentation_320_float16.tflite

[ ] 1.8 - Copy model to Android assets
         cp smartcane_segmentation_320_float16.tflite \
            android-app/app/src/main/assets/yolov8n_seg_320_float16.tflite

[ ] 1.9 - Build Android app
         cd android-app && ./gradlew clean assembleDebug

[ ] 1.10 - Verify successful build
         # Should end with: BUILD SUCCESSFUL in XXs
         cd ..

✅ PHASE 1 COMPLETE: Basic pipeline verified!


## PHASE 2: REAL DATA COLLECTION & ANNOTATION (1-2 weeks)
═══════════════════════════════════════════════════════════════════════════

### Step 2.1: Prepare for Collection
[ ] 2.1.1 - Read collection guidelines
         Minimum: 300 images (40+ per class)
         Recommended: 2400+ images (300+ per class)

[ ] 2.1.2 - Set up directory structure
         python train_custom_segmentation.py --prepare-dirs

[ ] 2.1.3 - Verify directory structure created
         ls -la data/images/
         ls -la data/labels/

### Step 2.2: Collect Images
[ ] 2.2.1 - Collect Person images (40-300)
         [ ] Standing poses
         [ ] Walking poses
         [ ] Sitting poses
         [ ] Various clothing
         [ ] Different angles
         [ ] Various lighting

[ ] 2.2.2 - Collect Furniture images (40-300)
         [ ] Chairs
         [ ] Tables
         [ ] Couches
         [ ] Beds
         [ ] Shelves
         [ ] Cabinets

[ ] 2.2.3 - Collect Vehicle images (40-300)
         [ ] Cars (front, side, back)
         [ ] Motorcycles
         [ ] Bikes
         [ ] Scooters
         [ ] Tricycles

[ ] 2.2.4 - Collect Animal images (30-300)
         [ ] Dogs
         [ ] Cats
         [ ] Birds
         [ ] Various sizes

[ ] 2.2.5 - Collect Pothole images (40-300)
         [ ] Small holes
         [ ] Large holes
         [ ] Cracks
         [ ] Road damage
         [ ] Various surfaces

[ ] 2.2.6 - Collect Water Puddle images (40-300)
         [ ] Small puddles
         [ ] Large puddles
         [ ] Rain-soaked areas
         [ ] Indoor spills

[ ] 2.2.7 - Collect Slippery Floor images (40-300)
         [ ] Wet floors
         [ ] Ice
         [ ] Glossy surfaces
         [ ] Smooth tiles

[ ] 2.2.8 - Collect Clear Path images (30-300)
         [ ] Empty hallways
         [ ] Clear walkways
         [ ] Safe areas
         [ ] Open spaces

### Step 2.3: Organize Images
[ ] 2.3.1 - Split images into train/val/test
         80% → data/images/train/
         10% → data/images/val/
         10% → data/images/test/

[ ] 2.3.2 - Verify file counts
         echo "Train:" && ls data/images/train/ | wc -l
         echo "Val:" && ls data/images/val/ | wc -l
         echo "Test:" && ls data/images/test/ | wc -l

### Step 2.4: Create Segmentation Annotations
[ ] 2.4.1 - Choose annotation tool
         [ ] CVAT (Professional) - See CUSTOM_MODEL_TRAINING.md
         [ ] Roboflow (Easiest) - https://roboflow.com/
         [ ] Label Studio (Free) - pip install label-studio

[ ] 2.4.2 - Set up annotation tool
         If CVAT:
         docker run -d -p 8080:8080 cvat/cvat:latest
         
         If Roboflow:
         Visit https://roboflow.com/ and create account
         
         If Label Studio:
         pip install label-studio && label-studio start

[ ] 2.4.3 - Create project
         [ ] Instance segmentation task (NOT bounding box)
         [ ] 8 classes: person, furniture, vehicle, animal, pothole, water_puddle, slippery_floor, clear_path

[ ] 2.4.4 - Annotate training images (80% of dataset)
         [ ] Use polygon tool to trace object boundaries
         [ ] Ensure precise segmentation masks
         [ ] All 8 classes represented in training set

[ ] 2.4.5 - Annotate validation images (10% of dataset)
         [ ] Quick validation coverage
         [ ] All classes included

[ ] 2.4.6 - Export annotations
         [ ] Export format: YOLO Segmentation (NOT COCO, NOT bounding boxes)
         [ ] Will generate .txt files with polygon coordinates

[ ] 2.4.7 - Organize label files
         data/labels/train/*.txt  (80% of labels)
         data/labels/val/*.txt    (10% of labels)
         data/labels/test/*.txt   (10% of labels)

### Step 2.5: Verify Dataset
[ ] 2.5.1 - Check label file format
         head -1 data/labels/train/image1.txt
         # Should look like: 0 0.45 0.2 0.55 0.2 0.6 0.4 ...

[ ] 2.5.2 - Verify all images have labels
         for img in data/images/train/*.jpg; do
             label="${img/images/labels}"
             label="${label/.jpg/.txt}"
             [ ! -f "$label" ] && echo "MISSING: $label"
         done

[ ] 2.5.3 - Check class distribution
         grep "^0 " data/labels/train/*.txt | wc -l  # person count
         grep "^1 " data/labels/train/*.txt | wc -l  # furniture count
         # ... repeat for other classes

[ ] 2.5.4 - Verify dataset.yaml exists
         cat data/dataset.yaml  # Should show path, train, val, test, nc: 8, names

✅ PHASE 2 COMPLETE: Real dataset prepared!


## PHASE 3: MODEL TRAINING (1-4 hours)
═══════════════════════════════════════════════════════════════════════════

[ ] 3.1 - Choose training setup
         [ ] CPU: Slower but works on any machine
         [ ] GPU: Much faster, requires NVIDIA GPU + CUDA

[ ] 3.2 - Start training (choose one based on hardware)
         
         CPU (basic):
         python train_custom_segmentation.py \
             --data-dir data --epochs 50 --batch 8 --device cpu
         
         GPU (recommended):
         python train_custom_segmentation.py \
             --data-dir data --epochs 100 --batch 32 --device 0 --patience 20
         
         GPU (production - slower but better accuracy):
         python train_custom_segmentation.py \
             --data-dir data --epochs 200 --batch 32 --device 0 \
             --lr0 0.01 --warmup-epochs 5

[ ] 3.3 - Monitor training (open new terminal)
         tensorboard --logdir runs/segment

[ ] 3.4 - Track training metrics
         tail -f runs/segment/smartcane_custom/results.csv
         # Watch for: mAP50 increasing, loss decreasing

[ ] 3.5 - If training stalls (loss not improving for 20 epochs)
         [ ] Increase data size
         [ ] Reduce learning rate
         [ ] Increase warmup epochs

[ ] 3.6 - Verify training completed
         ls -lh runs/segment/smartcane_custom/weights/best.pt
         # Should be ~20-50 MB

[ ] 3.7 - Review final metrics
         tail -1 runs/segment/smartcane_custom/results.csv
         # Check mAP50 ≥ 0.65 for good accuracy

✅ PHASE 3 COMPLETE: Model trained!


## PHASE 4: EXPORT & VALIDATION (30 minutes)
═════════════════════════════════════════════════════════════════════════

[ ] 4.1 - Export to TFLite (float16 for mobile)
         python train_custom_segmentation.py \
             --export-only runs/segment/smartcane_custom/weights/best.pt \
             --imgsz 320 --half

[ ] 4.2 - Verify model file
         ls -lh smartcane_segmentation_320_float16.tflite
         # Should be exactly 6.6 MB (±0.2 MB)

[ ] 4.3 - Copy to Android assets
         cp smartcane_segmentation_320_float16.tflite \
            android-app/app/src/main/assets/yolov8n_seg_320_float16.tflite

[ ] 4.4 - Verify model in assets
         ls -lh android-app/app/src/main/assets/*.tflite

[ ] 4.5 - Rebuild Android app
         cd android-app
         ./gradlew clean assembleDebug

[ ] 4.6 - Verify build success
         # Should show: BUILD SUCCESSFUL in XXs
         cd ..

✅ PHASE 4 COMPLETE: Model ready for Android!


## PHASE 5: DEPLOY & TEST ON DEVICE (30 minutes)
═══════════════════════════════════════════════════════════════════════════

[ ] 5.1 - Connect Android device via USB
         adb devices
         # Should show your device

[ ] 5.2 - Install app on device
         adb install -r android-app/app/build/outputs/apk/debug/app-debug.apk

[ ] 5.3 - Verify installation
         adb shell pm list packages | grep smartcane

[ ] 5.4 - Start app on device
         adb shell am start -n com.smartcane.gateway/.MainActivity

[ ] 5.5 - Verify camera starts automatically
         Visual check on device: Should show camera feed with overlays

[ ] 5.6 - Monitor logs
         adb logcat | grep smartcane
         # Look for: "Model loaded", "Inference successful"

[ ] 5.7 - Test obstacle detection
         [ ] Hold up person → should detect as "Person"
         [ ] Show furniture → should detect as "Furniture"
         [ ] Show all 8 classes
         [ ] Verify segmentation masks appear

[ ] 5.8 - Test edge cases
         [ ] Low light conditions
         [ ] Multiple objects
         [ ] Partially visible objects
         [ ] Fast movement

[ ] 5.9 - Check performance
         [ ] Inference < 500ms per frame
         [ ] No crashes
         [ ] Consistent detections

✅ PHASE 5 COMPLETE: Model deployed!


## PHASE 6: FIELD TESTING & OPTIMIZATION (1-2 weeks)
═══════════════════════════════════════════════════════════════════════════

[ ] 6.1 - Real-world testing
         [ ] Test in various environments
         [ ] Test with different users
         [ ] Collect failure cases

[ ] 6.2 - If accuracy is poor on specific classes
         Option A: Add more training data for that class
         Option B: Retrain with increased confidence threshold
         Option C: Use data augmentation

[ ] 6.3 - If false positives too high
         Increase class confidence threshold in TfliteObjectDetector.kt
         Lines around 95-105 in CLASS_CONFIDENCE_THRESHOLDS

[ ] 6.4 - If false negatives high (missing detections)
         Decrease class confidence threshold
         Or add more training data for that class

[ ] 6.5 - Performance optimization
         If inference too slow:
         [ ] Reduce input size (--imgsz 256)
         [ ] Use quantization (already using --half)
         
         If not accurate enough:
         [ ] Increase input size (--imgsz 640)
         [ ] Train longer (--epochs 200)

[ ] 6.6 - Iterate training
         # Repeat phases 2-5 with improved data

✅ PHASE 6 COMPLETE: Optimized model!


═══════════════════════════════════════════════════════════════════════════
                              FINAL CHECKLIST
═══════════════════════════════════════════════════════════════════════════

FUNCTIONALITY:
[ ] All 8 classes detected correctly
[ ] Segmentation masks are precise
[ ] Model runs on Android device
[ ] Inference < 500ms per frame
[ ] No crashes in normal operation

ACCURACY:
[ ] mAP50 ≥ 0.65 on validation set
[ ] All classes ≥ 70% accuracy
[ ] False positives < 10%
[ ] False negatives < 5%

DEPLOYMENT:
[ ] Model file in Android assets (6.6 MB)
[ ] Android app builds successfully
[ ] App runs on physical device
[ ] Camera starts automatically
[ ] Detections shown in real-time

DOCUMENTATION:
[ ] Training procedure documented
[ ] Model metrics recorded
[ ] Issues/improvements logged
[ ] Code changes committed

═══════════════════════════════════════════════════════════════════════════
                          ESTIMATED TIMELINE
═══════════════════════════════════════════════════════════════════════════

Phase 1 (Quick Test):        15 min  - 1 hour
Phase 2 (Data Collection):   1-2 weeks
Phase 3 (Training):          1-4 hours (GPU) / 8-16 hours (CPU)
Phase 4 (Export/Build):      30 min
Phase 5 (Deploy/Test):       30 min
Phase 6 (Optimization):      1-2 weeks

TOTAL: 2-4 weeks for production-ready model

═══════════════════════════════════════════════════════════════════════════
                           USEFUL COMMANDS
═══════════════════════════════════════════════════════════════════════════

# View training progress
tensorboard --logdir runs/segment

# Check model metrics
tail runs/segment/smartcane_custom/results.csv

# Monitor Android logs
adb logcat | grep smartcane

# Check GPU usage (during training)
watch -n 1 nvidia-smi

# Count images per class
for class in 0 1 2 3 4 5 6 7; do
    echo "Class $class: $(grep "^$class " data/labels/train/*.txt | wc -l)"
done

═══════════════════════════════════════════════════════════════════════════
                         DOCUMENTATION FILES
═══════════════════════════════════════════════════════════════════════════

CUSTOM_MODEL_README.md         → 5-min quick start guide
CUSTOM_MODEL_TRAINING.md       → Complete detailed guide (7 steps)
IMPLEMENTATION_SUMMARY.md      → Current status & timeline
PULL_REQUEST.md                → What changed and why
QUICK_REFERENCE.sh             → All commands in one file
This file (CHECKLIST.sh)       → Step-by-step progress tracker

═══════════════════════════════════════════════════════════════════════════

Good luck! 🎯 You've got this!

EOF
