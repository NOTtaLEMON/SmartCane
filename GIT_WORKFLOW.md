# Git Workflow - Push & Pull Commands for Team

## For You (To Push Changes)

### If You Haven't Pushed Yet
```bash
# Check current branch
git branch -v

# Ensure you're on phase-2-changes
git checkout phase-2-changes

# View unpushed commits
git log origin/phase-2-changes..HEAD

# Push to remote
git push origin phase-2-changes

# Verify push was successful
git log --oneline -5
```

### If You've Already Pushed
```bash
# Create a pull request on GitHub
# Or send teammates the pull command below
```

## For Your Teammates (To Pull Changes)

### Quick Pull
```bash
# From their SmartCane directory:
git pull origin phase-2-changes
```

### Detailed Pull (Step by Step)
```bash
# 1. Check current branch
git branch

# 2. Fetch latest from remote
git fetch origin

# 3. Switch to phase-2-changes branch
git checkout phase-2-changes

# 4. Pull the latest changes
git pull origin phase-2-changes

# 5. Verify you have the new files
ls -la train_custom_segmentation.py generate_sample_dataset.py
```

### Alternative: Create New Branch from phase-2-changes
```bash
# If teammates want to work on a separate branch
git checkout -b feature/custom-model-training origin/phase-2-changes

# Make changes if needed
# Then merge back when ready
```

## Summary of Changes

### New Files (for teammates to expect)
```
train_custom_segmentation.py        - YOLOv8 training pipeline
generate_sample_dataset.py          - Synthetic dataset generator
setup_custom_model.sh               - Setup script
CUSTOM_MODEL_README.md              - 5-min quick start
CUSTOM_MODEL_TRAINING.md            - Complete guide
IMPLEMENTATION_SUMMARY.md           - Status & timeline
PULL_REQUEST.md                     - What changed
QUICK_REFERENCE.sh                  - Command reference
CHECKLIST.sh                        - Progress tracker
README_CUSTOM_MODEL.md              - Navigation guide
```

### Modified Files
```
android-app/app/src/main/java/com/smartcane/gateway/TfliteObjectDetector.kt
  - Updated labelForClassIndex() for 8-class support
  - Added per-class confidence thresholds
  - Auto-detection of custom vs COCO models
```

## What Teammates Should Do After Pulling

### Step 1: Read Documentation (5 minutes)
```bash
cat CUSTOM_MODEL_README.md
```

### Step 2: Test Pipeline (15 minutes)
```bash
# Generate sample dataset
python generate_sample_dataset.py --images 50

# Train on sample data
python train_custom_segmentation.py --epochs 20 --batch 8 --device cpu

# Build Android app
cd android-app && ./gradlew assembleDebug
```

### Step 3: Verify Everything Works
```bash
# Should see: BUILD SUCCESSFUL in XXs
# This confirms the infrastructure is integrated correctly
```

## If Teammates Have Issues

### Issue: "Python not found"
```bash
# They need to install Python
# Or activate virtual environment:
source venv/bin/activate  # macOS/Linux
# or
venv\Scripts\activate  # Windows
```

### Issue: "TensorFlow import error"
```bash
pip install tensorflow>=2.21.0
```

### Issue: "ultralytics not found"
```bash
pip install ultralytics
```

### Issue: "Android build fails"
```bash
cd android-app
./gradlew clean
./gradlew assembleDebug --stacktrace
```

## Communication Template for Teammates

You can share this message with your team:

---

### 📦 New Custom YOLOv8 Integration - Please Pull

Hi team,

I've pushed custom YOLOv8 segmentation model infrastructure to the `phase-2-changes` branch. This allows us to train domain-specific obstacle detection models instead of using the generic COCO model.

**To get the changes:**
```bash
git pull origin phase-2-changes
```

**What's included:**
- Training pipeline for 8-class custom models
- Sample dataset generator (no real data needed for testing)
- Complete documentation and guides
- Updated Android detector with per-class confidence thresholds

**Quick Test (everyone should do this):**
```bash
python generate_sample_dataset.py --images 50
python train_custom_segmentation.py --epochs 20 --batch 8 --device cpu
cd android-app && ./gradlew assembleDebug
```

**Next Steps:**
- Data scientists: Start collecting training images
- Developers: Test the pipeline with sample data
- Leads: Review IMPLEMENTATION_SUMMARY.md for timeline

**Documentation:**
- Quick start: `CUSTOM_MODEL_README.md`
- Commands: `QUICK_REFERENCE.sh`
- Progress: `CHECKLIST.sh`
- Details: `CUSTOM_MODEL_TRAINING.md`

Let me know if you hit any issues!

---

## Current Git Status

```bash
# View all commits on phase-2-changes
git log --oneline origin/phase-2-changes | head -10

# View commits ahead of main
git log --oneline main..origin/phase-2-changes

# Detailed diff of what changed
git diff main origin/phase-2-changes --stat
```

## Merging to Main (When Ready)

```bash
# Option 1: Merge via GitHub pull request
# Option 2: Merge locally
git checkout main
git pull origin main
git merge phase-2-changes
git push origin main
```

## Branch Management

```bash
# Delete local branch (after merging)
git branch -d phase-2-changes

# Delete remote branch
git push origin --delete phase-2-changes

# List all branches
git branch -a
```

---

**Quick Help Sheet for Teammates:**

| Task | Command |
|------|---------|
| Pull changes | `git pull origin phase-2-changes` |
| Check files pulled | `ls -la train_custom_segmentation.py` |
| Read guide | `cat CUSTOM_MODEL_README.md` |
| Test pipeline | `python generate_sample_dataset.py --images 50` |
| Build Android | `cd android-app && ./gradlew assembleDebug` |
| View all docs | `ls -la *.md` |

---

**Status**: 🟢 Ready for Team Integration
