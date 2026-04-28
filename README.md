# 🦯 Smart Cane Clip-On — Complete Project Guide

## What is Smart Cane?

**Smart Cane** is an intelligent cane system that uses sensors and AI to help users navigate safely. It detects obstacles, monitors the user's movements, and can alert them (or caregivers) if a fall is detected. Think of it as a "smart assistant" that clips onto a regular cane to make it safer.

---

## 🎯 Project Overview

This project has **4 main modules** that work together:

### **Module A: Firmware (Cane_Firmware.ino)**
- **What it does:** Runs on the ESP32 microcontroller (the "brain" of the cane)
- **Job:** Reads data from distance sensors (ultrasonic) and an accelerometer
  - Measures distance to obstacles in front and below
  - Detects if the user has fallen
  - Reads light/brightness levels
- **Output:** Sends this data over USB Serial (like "100,200,0,500") to the dashboard

### **Module B: Android Service (Android_SOS_Service.kt)**
- **What it does:** Runs on an Android phone paired with the cane
- **Job:** 
  - Receives alerts from the cane
  - Can trigger an SOS (emergency call/SMS) if a fall is detected
  - Sends notifications to the user or emergency contacts

### **Module C: Vision/AI (Universal_Vision.py)**
- **What it does:** Processes camera/visual input
- **Job:**
  - Uses YOLO (a fast AI model) to detect objects, people, pets, etc. around the user
  - Recognizes hazards (stairs, obstacles, other people)
  - Logs detection results to `vision.log`
  - Could eventually trigger warnings via the cane

### **Module D: Dashboard (Project_Dashboard.py)** ← **YOU ARE HERE**
- **What it does:** The control center — displays everything on a screen
- **Job:**
  - Reads sensor data from the ESP32 over USB Serial
  - Displays live graphs of distance, light, and movement
  - Shows AI detections from Module C
  - Monitors alerts (falls, obstacles getting too close, low light)
  - Has a **Mock Mode** (for testing without hardware)

---

## 🔧 Hardware Components

| Component | Purpose |
|-----------|---------|
| **ESP32** | Microcontroller that reads sensors and sends data |
| **Ultrasonic Sensors** | Measure distance (front + downward) |
| **Accelerometer** | Detects sudden movements (falls) |
| **Light Sensor** | Measures brightness |
| **USB Cable** | Connects ESP32 to computer for Dashboard |
| **Android Phone** | Sends alerts / SOS if needed |

---

## 📊 How Data Flows

```
    ESP32 (Sensors)
        ↓
    USB Serial → Computer
        ↓
    Project_Dashboard.py (reads data)
        ↓
    ├─→ Live Graphs (front distance, drop distance, light)
    ├─→ Alerts (if fall detected or obstacle too close)
    ├─→ Vision AI Overlay (from Universal_Vision.py)
    └─→ Sends alerts to Android app
```

---

## 🚀 Quick Start

### **Prerequisites**
- Python 3.9 or higher
- USB cable to connect ESP32
- (Optional) Android phone for alerts

### **Installation**

1. **Clone/Download this project**
   ```bash
   cd /Users/anushka/untitled\ folder\ 3/HELLOP/SmartCane
   ```

2. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   ```
   This installs:
   - `streamlit` — for the dashboard UI
   - `pyserial` — to read USB Serial data
   - `pandas` — for data handling
   - `opencv-python` — for vision processing (if used)

3. **Run the Dashboard**
   ```bash
   streamlit run Project_Dashboard.py
   ```
   - A browser window opens at `http://localhost:8501`
   - You'll see the dashboard UI

---

## 📱 Using the Dashboard

### **Left Sidebar (Settings)**

| Setting | What it does |
|---------|------------|
| **Mock Mode** | If ON, generates fake sensor data (no hardware needed) |
| **Serial Port** | Select the USB port where ESP32 is connected |
| **Baud Rate** | Data speed (leave at 115200) |
| **Vision overlay path** | Path to `vision.log` from Module C |
| **History window** | How many seconds of data to show in graphs |
| **▶ Start stream** | Toggle to start/pause data collection |

### **Main Display**

- **4 Metrics (top):**
  - Front distance (mm)
  - Drop distance (mm)
  - Fall status (⚠ YES or ok)
  - Light level

- **Vision Box:**
  - Shows what the AI detected (e.g., "Car:0.82, Person:0.91")

- **3 Live Graphs:**
  - Front distance over time
  - Drop distance over time
  - Light level over time

---

## 🧪 Testing Without Hardware (Mock Mode)

1. Start the dashboard:
   ```bash
   streamlit run Project_Dashboard.py
   ```

2. In the sidebar:
   - Turn **ON** "Mock Mode (no hardware)"
   - Click "▶ Start stream"

3. Watch the fake data appear in the graphs and metrics!
   - Occasionally you'll see a fall alert (simulated)

---

## 📝 Data Format (ESP32 → Dashboard)

The ESP32 sends data like this every ~100ms:

```
dist_fwd,dist_drop,fall_flag,light_val
045,180,0,550
```

| Field | Meaning | Unit |
|-------|---------|------|
| `dist_fwd` | Distance to obstacle in front | mm |
| `dist_drop` | Distance to ground below | mm |
| `fall_flag` | 1 = fall detected, 0 = normal | binary |
| `light_val` | Brightness reading | 0–1023 (ADC value) |

---

## 🚨 Alert System (New Feature)

The dashboard can now show **alerts** when:
- A fall is detected
- Front distance gets too close (obstacle warning)
- Drop distance is too low (edge warning)
- Light is too dim

Alerts are logged with timestamps and can be saved to a file.

---

## 📂 File Guide

| File | Purpose |
|------|---------|
| `Cane_Firmware.ino` | Arduino sketch for ESP32 (sensors + serial output) |
| `Project_Dashboard.py` | Main dashboard app (Streamlit) |
| `Universal_Vision.py` | AI vision processing (optional) |
| `Android_SOS_Service.kt` | Android emergency alert service |
| `requirements.txt` | Python package list |
| `README.md` | This file |

---

## 🔌 Troubleshooting

### **"pyserial not installed"**
Run:
```bash
pip install pyserial
```

### **"Serial port not detected"**
- Check that ESP32 is plugged in via USB
- Try different USB cables (some are charge-only)
- Restart the dashboard

### **"No data appearing in graphs"**
- Make sure "▶ Start stream" is ON
- In Mock Mode? Data should appear in ~1 second
- Check the serial port selection

### **"Dashboard won't start"**
Run:
```bash
pip install streamlit pandas pyserial
```

---

## 📚 Next Steps

1. **Test with Mock Mode** — get familiar with the UI
2. **Connect ESP32** — plug in hardware and switch off Mock Mode
3. **Add AI Vision** — run `Universal_Vision.py` to detect objects
4. **Set Alerts** — configure thresholds for warnings
5. **Deploy Android App** — send alerts to phone for emergencies

---

## 🤝 Contributing

If you find bugs or want to add features:
1. Create a new branch: `git checkout -b your-feature-name`
2. Make changes
3. Test in Mock Mode
4. Commit: `git commit -m "describe your change"`
5. Push and create a Pull Request

---

## 📞 Support

For questions or issues:
- Check the comments in each `.py` file for technical details
- Review the hardware schematics (if available)
- Test in Mock Mode first to isolate software vs. hardware issues

---

## 📄 License

This project is part of the SmartCane initiative.

---

**Happy coding! 🦯**
