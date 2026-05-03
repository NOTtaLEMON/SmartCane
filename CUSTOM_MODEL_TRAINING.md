# Smart Cane Custom Segmentation Model - Dataset Preparation Guide

## Overview
To train a custom YOLOv8 segmentation model for accurate obstacle detection, you need to:
1. Collect images of various obstacles
2. Create segmentation masks/labels
3. Train the model
4. Deploy to Android

## Step 1: Collect Training Images

### Recommended Dataset Composition
- **Total images**: 300-500+ (80% train, 10% val, 10% test)
- **Classes to capture**:
  - **Person** (50 images): Different poses, clothing, angles
  - **Furniture** (40 images): Chairs, tables, couches, beds, shelves
  - **Vehicle** (40 images): Cars, bikes, motorcycles, scooters
  - **Animal** (30 images): Dogs, cats, birds
  - **Pothole** (40 images): Road damage, holes, cracks
  - **Water Puddle** (40 images): Standing water, wet areas
  - **Slippery Floor** (40 images): Ice, wet floor, smooth surfaces
  - **Clear Path** (30 images): Safe walking areas, empty spaces

### Image Requirements
- **Resolution**: 320×320 or higher (640×640 preferred)
- **Format**: JPG, PNG
- **Lighting**: Various conditions (daylight, indoor, low-light, shadows)
- **Angles**: Multiple perspectives for each obstacle type
- **Real-world scenarios**: Ground-level perspective (as user would see)

### Data Sources
- **Your own**: Take photos with smartphone at ground level
- **Public datasets**:
  - COCO dataset: https://cocodataset.org/
  - ImageNet: https://www.image-net.org/
  - OpenImages: https://storage.googleapis.com/openimages/web/index.html
  - Roboflow: https://roboflow.com/

## Step 2: Prepare Directory Structure

```bash
cd SmartCane
python train_custom_segmentation.py --prepare-dirs

# This creates:
# data/
# ├── images/
# │   ├── train/     (put 80% of images here)
# │   ├── val/       (put 10% of images here)
# │   └── test/      (put 10% of images here)
# └── labels/
#     ├── train/     (labels will go here)
#     ├── val/
#     └── test/
```

## Step 3: Create Segmentation Labels

### YOLO Segmentation Label Format
Each image needs a `.txt` file with the same name in the corresponding labels folder.

**Format**: 
```
<class_id> <x1> <y1> <x2> <y2> ... <xn> <yn>
```

**Where**:
- `class_id`: 0-7 (person=0, furniture=1, vehicle=2, animal=3, pothole=4, water_puddle=5, slippery_floor=6, clear_path=7)
- `x1 y1 x2 y2 ...`: Normalized polygon coordinates (0-1, clockwise around the object)

**Example**:
```
0 0.45 0.2 0.55 0.2 0.6 0.4 0.55 0.6 0.45 0.6 0.4 0.4
```

### Tools for Creating Labels

#### Option 1: CVAT (Recommended for Segmentation)
```bash
# Install CVAT
docker run -d -p 8080:8080 cvat/cvat:latest

# Open browser: http://localhost:8080
# Create project with segmentation tasks
# Export in YOLO format
```

#### Option 2: Roboflow
1. Sign up: https://roboflow.com/
2. Create project with segmentation task
3. Upload images
4. Annotate in web interface
5. Export as YOLO Segmentation format
6. Download dataset

#### Option 3: Label Studio
```bash
pip install label-studio
label-studio start

# Open browser: http://localhost:8080
# Create segmentation project
# Annotate images
# Export as YOLO format
```

#### Option 4: Python Script (Manual)
For quick labeling, create a simple script:

```python
# quick_label.py - Simple point-click segmentation labeler
import cv2
import json
from pathlib import Path

CLASSES = {
    '0': 'person',
    '1': 'furniture',
    '2': 'vehicle',
    '3': 'animal',
    '4': 'pothole',
    '5': 'water_puddle',
    '6': 'slippery_floor',
    '7': 'clear_path'
}

def label_image(image_path, label_path):
    img = cv2.imread(image_path)
    h, w = img.shape[:2]
    
    points = []
    
    def mouse_click(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            points.append((x, y))
            cv2.circle(img, (x, y), 3, (0, 255, 0), -1)
            cv2.imshow('Label', img)
        elif event == cv2.EVENT_RBUTTONDOWN:
            if points:
                points.pop()
                cv2.imshow('Label', img)
    
    cv2.imshow('Label', img)
    cv2.setMouseCallback('Label', mouse_click)
    
    print(f"Click to add points for {CLASSES[input('Class ID (0-7): ')]}")
    print("Right-click to undo, Press 's' to save, 'q' to skip")
    
    while True:
        key = cv2.waitKey(0)
        if key == ord('s'):  # Save
            class_id = input("Class ID (0-7): ")
            # Normalize to 0-1
            norm_points = [(x/w, y/h) for x, y in points]
            with open(label_path, 'w') as f:
                coords = ' '.join(f'{x:.4f} {y:.4f}' for x, y in norm_points)
                f.write(f"{class_id} {coords}\n")
            break
        elif key == ord('q'):  # Skip
            break
    
    cv2.destroyAllWindows()

# Usage
from pathlib import Path
for img in Path('data/images/train').glob('*.jpg'):
    label = Path('data/labels/train') / (img.stem + '.txt')
    if not label.exists():
        label_image(str(img), str(label))
```

## Step 4: Validate Dataset

```bash
python train_custom_segmentation.py --prepare-dirs

# Check that:
# - All train images have corresponding labels in train/
# - All val images have corresponding labels in val/
# - All test images have corresponding labels in test/
# - Labels are in correct format (space-separated numbers)

# Verify labels:
for label in data/labels/train/*.txt; do
    echo "$label:"; head -1 "$label"
done
```

## Step 5: Train the Model

### Basic Training (CPU)
```bash
python train_custom_segmentation.py \
    --data-dir data \
    --epochs 50 \
    --batch 8 \
    --imgsz 320 \
    --device cpu
```

### With GPU (faster)
```bash
python train_custom_segmentation.py \
    --data-dir data \
    --epochs 100 \
    --batch 32 \
    --imgsz 320 \
    --device 0
```

### Resume Training
```bash
python train_custom_segmentation.py \
    --data-dir data \
    --epochs 150 \
    --resume
```

### Training Output
```
runs/segment/smartcane_custom/
├── weights/
│   ├── best.pt    (best model - use for export)
│   └── last.pt    (latest checkpoint)
├── results.csv    (training metrics)
└── confusion_matrix.png
```

## Step 6: Export to TFLite

### Export Best Model
```bash
python train_custom_segmentation.py \
    --export-only runs/segment/smartcane_custom/weights/best.pt \
    --imgsz 320 \
    --half
```

### Output
```
smartcane_segmentation_320_float16.tflite  (best for mobile)
```

## Step 7: Deploy to Android

```bash
# Copy model to assets
cp smartcane_segmentation_320_float16.tflite \
   android-app/app/src/main/assets/

# Rename if needed to match app expectations
mv android-app/app/src/main/assets/smartcane_segmentation_320_float16.tflite \
   android-app/app/src/main/assets/yolov8n_seg_320_float16.tflite

# Build and run
cd android-app
./gradlew assembleDebug

# Install APK
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

## Troubleshooting

### Training Issues

**Model not improving**
- Increase dataset size (add more images)
- Increase epochs
- Reduce learning rate

**Out of memory**
- Reduce batch size: `--batch 8`
- Reduce image size: `--imgsz 320`
- Use CPU: `--device cpu`

**Labels not recognized**
- Check format: `class_id x1 y1 x2 y2 ...`
- Normalize coordinates to 0-1
- Ensure .txt file names match image names

### Android Issues

**Model not loading**
- Check assets folder has correct filename
- Verify model size < 100MB
- Check numClasses matches (should be 8)

**Only detecting person**
- Increase training epochs
- Add more diverse training images
- Lower confidence threshold in code (0.35-0.45)

**Poor accuracy on specific class**
- Add more training images of that class
- Use data augmentation (flip, rotate, etc.)
- Increase class-specific confidence threshold

## Performance Tips

- **Faster training**: Use GPU (`--device 0`)
- **Better accuracy**: Train with `--epochs 200` and larger `--batch 32`
- **Mobile inference**: Use `--half` for float16 quantization (6.6MB model)
- **Validation**: Use `--epochs 100` with early stopping patience

## Next Steps

1. Collect 300+ diverse images
2. Create labels using CVAT or Roboflow
3. Train model (100+ epochs recommended)
4. Export to TFLite
5. Deploy to Android
6. Test and iterate with more data

Good luck! 🎯
