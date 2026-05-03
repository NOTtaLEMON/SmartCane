# Custom YOLOv8 Segmentation Model for Smart Cane

## Overview

The Smart Cane app now includes infrastructure to train and deploy custom YOLOv8 segmentation models for accurate 8-class obstacle detection. The generic COCO model has been replaced with a custom model architecture that can learn domain-specific patterns.

## Quick Start (5 minutes)

### Option A: Test with Sample Data (No Real Data Needed)

```bash
# 1. Generate synthetic dataset
python generate_sample_dataset.py --images 100

# 2. Train model (takes 5-10 minutes on CPU, 1-2 minutes on GPU)
python train_custom_segmentation.py --epochs 50 --batch 8

# 3. Export to TFLite
python train_custom_segmentation.py --export-only runs/segment/smartcane_custom/weights/best.pt --half

# 4. Deploy to Android
cp smartcane_segmentation_320_float16.tflite android-app/app/src/main/assets/
cd android-app && ./gradlew assembleDebug
```

### Option B: Train with Your Own Data

```bash
# 1. Prepare directories
python train_custom_segmentation.py --prepare-dirs

# 2. Add your images and labels to:
# - data/images/train/, data/images/val/, data/images/test/
# - data/labels/train/, data/labels/val/, data/labels/test/

# 3. Train
python train_custom_segmentation.py --epochs 100 --batch 16 --device 0  # Add --device 0 for GPU

# 4. Export and deploy (same as above)
```

## 8-Class Obstacle Taxonomy

| ID | Class | Purpose | Confidence |
|----|-------|---------|------------|
| 0 | Person | Detect people in path | 0.35 (aggressive) |
| 1 | Furniture | Chairs, tables, couches | 0.40 |
| 2 | Vehicle | Cars, bikes, scooters | 0.35 (aggressive) |
| 3 | Animal | Dogs, cats, birds | 0.40 |
| 4 | Pothole | Road damage, holes | 0.45 |
| 5 | Water Puddle | Standing water | 0.50 |
| 6 | Slippery Floor | Ice, wet surfaces | 0.50 |
| 7 | Clear Path | Safe to walk | 0.60 (conservative) |

## Architecture

```
User collects/provides images
         ↓
Annotate with segmentation masks (CVAT/Roboflow/Label Studio)
         ↓
Train custom YOLOv8 model (train_custom_segmentation.py)
         ↓
Export to TFLite (6.6MB float16)
         ↓
Deploy to Android (TfliteObjectDetector.kt)
         ↓
Real-time inference on phone camera (CaneVisionActivity.kt)
```

## Files

| File | Purpose |
|------|---------|
| `train_custom_segmentation.py` | Training pipeline with dataset prep, training, TFLite export |
| `generate_sample_dataset.py` | Generate synthetic dataset for testing |
| `setup_custom_model.sh` | Quick setup script with instructions |
| `CUSTOM_MODEL_TRAINING.md` | Detailed training guide |
| `TfliteObjectDetector.kt` | Updated Android detector with per-class thresholds |
| `CaneVisionActivity.kt` | Android vision activity with real-time inference |

## Training Parameters

### Quick Test (Sample Data)
```bash
python train_custom_segmentation.py \
    --epochs 50 \
    --batch 8 \
    --imgsz 320 \
    --device cpu
```

### Production (Real Data)
```bash
python train_custom_segmentation.py \
    --epochs 100 \
    --batch 32 \
    --imgsz 320 \
    --device 0 \
    --patience 20
```

### Advanced Tuning
```bash
python train_custom_segmentation.py \
    --epochs 200 \
    --batch 32 \
    --imgsz 640 \
    --device 0 \
    --lr0 0.01 \
    --lrf 0.001 \
    --patience 25 \
    --warmup-epochs 5
```

## Android Integration

### Model Loading
The `TfliteObjectDetector.kt` automatically:
1. Checks if model has 8 classes (custom model) or 80 classes (COCO)
2. Uses `SMART_CANE_LABELS` for custom model
3. Uses `COCO_LABELS` for generic model
4. Applies per-class confidence thresholds

### Model Detection
```kotlin
val isCustomSegModel = numClasses == SMART_CANE_LABELS.size && numClasses != 80

val threshold = if (isCustomSegModel && c in CLASS_CONFIDENCE_THRESHOLDS) {
    CLASS_CONFIDENCE_THRESHOLDS[c] ?: CONF_THRESHOLD
} else {
    CONF_THRESHOLD
}
```

### Deployment
```bash
# Copy model
cp smartcane_segmentation_320_float16.tflite \
   android-app/app/src/main/assets/yolov8n_seg_320_float16.tflite

# Build
cd android-app
./gradlew assembleDebug

# Install
adb install -r app/build/outputs/apk/debug/app-debug.apk

# Run
adb shell am start -n com.smartcane.gateway/com.smartcane.gateway.MainActivity
```

## Dataset Preparation

### Image Collection
- **Total**: 300-500+ images recommended
- **Distribution**: 80% train, 10% val, 10% test
- **Quality**: Various lighting, angles, backgrounds
- **Classes**: Ensure all 8 classes are well-represented

### Annotation Tools

**CVAT (Recommended)**
```bash
docker run -d -p 8080:8080 cvat/cvat:latest
# Navigate to http://localhost:8080
# Create segmentation project → Annotate → Export as YOLO
```

**Roboflow (Easiest)**
```
1. Sign up: https://roboflow.com/
2. Create project (instance segmentation)
3. Upload images
4. Annotate in web UI
5. Export as YOLO Segmentation
6. Download dataset
```

**Label Studio**
```bash
pip install label-studio
label-studio start
# Create segmentation task → Export YOLO format
```

### Label Format
```
<class_id> <x1> <y1> <x2> <y2> ... <xn> <yn>
```

Example:
```
0 0.45 0.2 0.55 0.2 0.6 0.4 0.55 0.6 0.45 0.6 0.4 0.4
1 0.1 0.1 0.2 0.1 0.25 0.4 0.15 0.5 0.05 0.4
```

## Troubleshooting

### Training

**Model not improving**
- Add more training images
- Increase epochs: `--epochs 200`
- Reduce learning rate: `--lr0 0.005`

**Out of memory**
- Reduce batch size: `--batch 8`
- Use smaller images: `--imgsz 320`
- Use CPU: `--device cpu`

**Poor accuracy on specific class**
- Add more images of that class
- Increase training data variety
- Adjust confidence threshold in Android code

### Android

**App crashes on inference**
- Check model file exists in assets
- Verify model size < 100MB
- Check logcat: `adb logcat | grep smartcane`

**Only detecting one class**
- Check training completed successfully
- Verify all 8 classes in dataset
- Increase training epochs

**Slow inference**
- Use `--half` for float16 quantization
- Reduce input size: `--imgsz 320`
- Ensure model file is optimized

## Performance

| Metric | Value |
|--------|-------|
| Model Size (float16) | 6.6 MB |
| Input Size | 320×320 |
| Inference Time | ~200-300ms (depends on device) |
| Output Classes | 8 |
| Segmentation Masks | Yes |
| Bounding Boxes | Yes |

## Next Steps

1. **Immediate**: Run sample dataset test
   ```bash
   python generate_sample_dataset.py --images 100
   python train_custom_segmentation.py --epochs 30 --batch 8
   ```

2. **Week 1**: Collect real training data
   - Take 300+ photos of obstacles at ground level
   - Annotate with segmentation masks

3. **Week 2**: Train production model
   - Train with real data (100+ epochs)
   - Validate accuracy on test set

4. **Week 3**: Deploy and iterate
   - Deploy to Android
   - Test in real environments
   - Fine-tune thresholds based on real-world performance

## Support

- **Training Issues**: Check `runs/segment/smartcane_custom/results.csv` for training metrics
- **Android Issues**: Use `adb logcat` to check for errors
- **Annotation Help**: See `CUSTOM_MODEL_TRAINING.md` for detailed guide

---

**Status**: ✅ Infrastructure Complete, Awaiting Dataset
