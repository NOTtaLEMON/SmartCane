# 📱 Build & Deploy APK Guide

## Quick Start (3 steps)

### **Step 1: Push Your Code**
```bash
cd /Users/anushka/untitled\ folder\ 3/HELLOP/SmartCane

# Check changes
git status

# Add changes
git add android-app/app/src/main/java/com/smartcane/gateway/TfliteObjectDetector.kt
git add TREE_DETECTION_INTEGRATION.md

# Commit and push
git commit -m "Add tree detection (class 8) with optimized thresholds"
git push origin phase-2-changes
```

### **Step 2: Build APK**

**For Testing (Debug APK - Faster):**
```bash
cd /Users/anushka/untitled\ folder\ 3/HELLOP/SmartCane/android-app
./gradlew assembleDebug
```

**For Release (Production APK - Slower, smaller file):**
```bash
cd /Users/anushka/untitled\ folder\ 3/HELLOP/SmartCane/android-app
./gradlew assembleRelease
```

### **Step 3: Find & Share APK**

**Debug APK Location:**
```bash
android-app/app/build/outputs/apk/debug/app-debug.apk
```

**Release APK Location:**
```bash
android-app/app/build/outputs/apk/release/app-release.apk
```

---

## 📥 Send to Teammates

### **Option A: Email/Cloud Share**
```bash
# Copy debug APK to Desktop for easy sharing
cp android-app/app/build/outputs/apk/debug/app-debug.apk ~/Desktop/SmartCane-debug.apk

# Or release APK
cp android-app/app/build/outputs/apk/release/app-release.apk ~/Desktop/SmartCane-release.apk
```

### **Option B: Push to GitHub**
```bash
# Add APK to git (if needed for binary releases)
git add android-app/app/build/outputs/apk/debug/app-debug.apk
git commit -m "Add debug APK for testing"
git push origin phase-2-changes
```

### **Option C: Create GitHub Release**
```bash
# On GitHub:
# 1. Go to Releases
# 2. Create new release
# 3. Upload APK file
# 4. Teammates can download from releases page
```

---

## 🔍 APK File Comparison

| Type | Size | Speed | Purpose |
|------|------|-------|---------|
| **Debug** | ~50-70 MB | Fast (2-5 min) | Testing & development |
| **Release** | ~30-40 MB | Slower (5-10 min) | Production, smaller file |

**Recommendation:** Use **Debug APK** for testing, **Release APK** for final distribution.

---

## 📋 Installation Instructions for Teammates

After your teammate receives the APK:

### **On Android Device:**
```bash
# Connect device via USB
adb install app-debug.apk

# Or enable "Unknown Sources" and sideload via USB
```

### **On Emulator:**
```bash
# With emulator running
adb install app-debug.apk

# Or drag & drop APK into emulator window
```

### **Verify Installation:**
```bash
# Check app is installed
adb shell pm list packages | grep smartcane

# Launch app
adb shell am start -n com.smartcane.gateway/.MainActivity
```

---

## ✅ What's Included in APK

✅ Tree detection (class 8)  
✅ 9-class object detection  
✅ Optimized thresholds:
- Person: 35% (aggressive)
- Vehicle: 35% (aggressive)
- Tree: 45% (medium)
- Pothole: 50% (hazard)
- Water Puddle: 50% (hazard)
- Slippery Floor: 50% (hazard)
- Furniture: 45%
- Animal: 45%
- Clear Path: 60%

✅ Updated TfliteObjectDetector  
✅ YOLOv8 segmentation model (6.9 MB)  
✅ Android SOS Service  
✅ WiFi integration  

---

## 🚀 Build Commands Summary

```bash
# Navigate to project
cd /Users/anushka/untitled\ folder\ 3/HELLOP/SmartCane/android-app

# Clean build
./gradlew clean build

# Build debug APK only (faster)
./gradlew assembleDebug

# Build release APK
./gradlew assembleRelease

# View build output
./gradlew assembleDebug --info

# Check for errors
./gradlew check
```

---

## 📊 Build Time Estimates

| Action | Time |
|--------|------|
| Clean | 30s |
| Download dependencies | 2-3 min (first time) |
| Build debug APK | 2-5 min |
| Build release APK | 5-10 min |

---

## ⚠️ Troubleshooting

**"No Java Runtime found"**
```bash
# Install Java Development Kit (JDK)
# macOS: brew install openjdk
# Or download from: https://www.oracle.com/java/technologies/downloads/
```

**"Gradle wrapper permission denied"**
```bash
chmod +x ./gradlew
./gradlew assembleDebug
```

**"Build fails with dependency errors"**
```bash
# Clear cache and rebuild
./gradlew clean --refresh-dependencies build
```

---

## 📝 For Your Teammates

Share this message:

> **New APK Ready for Testing!**
> 
> **What's New:**
> - ✅ Tree detection added (class 8)
> - ✅ 9-class object detection system
> - ✅ Optimized confidence thresholds
> 
> **To Install:**
> 1. Download APK from [link]
> 2. Enable "Unknown Sources" on phone
> 3. Open APK file to install
> 4. Open Smart Cane app
> 5. Click "VISION" to test detections
> 
> **Test Objects:**
> - Point at person → should detect (35% threshold)
> - Point at tree → should detect (45% threshold)
> - Point at vehicle → should detect (35% threshold)
> - Point at pothole → should detect (50% threshold)

---

**Ready to build!** Run `./gradlew assembleDebug` 🚀
