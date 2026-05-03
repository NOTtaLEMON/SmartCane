#!/bin/bash

# Quick Start: Train Custom Smart Cane Segmentation Model
# This script prepares the environment and starts training

set -e

echo "=========================================="
echo "Smart Cane Custom Segmentation - Quick Start"
echo "=========================================="
echo ""

# Check Python
if ! command -v python &> /dev/null; then
    echo "❌ Python not found. Please install Python 3.9+"
    exit 1
fi

# Activate venv
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
    echo "✓ Virtual environment activated"
fi

# Check dependencies
echo "Checking dependencies..."
pip install -q ultralytics opencv-python pyyaml pillow 2>/dev/null || {
    echo "Installing required packages..."
    pip install ultralytics opencv-python pyyaml pillow
}
echo "✓ Dependencies installed"

# Step 1: Prepare directory structure
echo ""
echo "Step 1: Preparing directory structure..."
python train_custom_segmentation.py --prepare-dirs
echo "✓ Created data/ directory structure"

# Step 2: Create sample data README
echo ""
echo "Step 2: Directory structure ready"
echo ""
echo "Next steps:"
echo ""
echo "1. COLLECT IMAGES"
echo "   - Place images in: data/images/train/, data/images/val/, data/images/test/"
echo "   - (80% train, 10% val, 10% test split)"
echo ""
echo "2. CREATE LABELS (Choose one method):"
echo ""
echo "   A) Using CVAT:"
echo "      docker run -d -p 8080:8080 cvat/cvat:latest"
echo "      Open http://localhost:8080 and export as YOLO Segmentation format"
echo ""
echo "   B) Using Roboflow:"
echo "      1. Sign up: https://roboflow.com/"
echo "      2. Create project, upload images"
echo "      3. Annotate and export as YOLO format"
echo ""
echo "   C) Using Label Studio:"
echo "      pip install label-studio"
echo "      label-studio start"
echo "      Create segmentation project and export"
echo ""
echo "   Place .txt labels next to images:"
echo "   - data/labels/train/*.txt  (for train images)"
echo "   - data/labels/val/*.txt    (for val images)"
echo "   - data/labels/test/*.txt   (for test images)"
echo ""
echo "3. TRAIN THE MODEL"
echo "   Basic (CPU):"
echo "   python train_custom_segmentation.py --epochs 50 --batch 8"
echo ""
echo "   With GPU (faster):"
echo "   python train_custom_segmentation.py --epochs 100 --batch 32 --device 0"
echo ""
echo "4. EXPORT TO TFLITE"
echo "   python train_custom_segmentation.py --export-only runs/segment/smartcane_custom/weights/best.pt --half"
echo ""
echo "5. DEPLOY TO ANDROID"
echo "   cp smartcane_segmentation_320_float16.tflite android-app/app/src/main/assets/"
echo "   cd android-app && ./gradlew assembleDebug"
echo ""
echo "=========================================="
echo ""
echo "For detailed guide, see: CUSTOM_MODEL_TRAINING.md"
echo ""
