# Smart Cane Firmware Setup Guide

## Overview
This guide covers the setup and configuration of the ESP32 Smart Cane firmware with dual-sensor support (TF-LUNA LIDAR + VL53L0X ToF) and fall detection via MPU6050.

---

## Hardware Requirements

### Sensors
- **TF-Luna LiDAR** - Front obstacle detection (via UART2)
- **VL53L0X ToF Sensor** - Downward drop detection (via I2C)
- **MPU6050** - Fall detection accelerometer (via I2C)
- **LDR (Light Sensor)** - Ambient light detection (analog pin)
- **16x2 I2C LCD Display** - Status display

### Microcontroller & Peripherals
- ESP32 DevKit or equivalent
- LED (GPIO 2) - Light indicator
- Buzzer (GPIO 4) - Proximity/fall alert
- USB cable for programming

---

## Pin Configuration

| Component | Pin | Type |
|-----------|-----|------|
| TF-Luna RX | GPIO 16 | UART2 RX |
| TF-Luna TX | GPIO 17 | UART2 TX |
| VL53L0X/LCD SDA | GPIO 21 | I2C SDA |
| VL53L0X/LCD SCL | GPIO 22 | I2C SCL |
| MPU6050 | 0x68 | I2C Address |
| LCD | 0x27 | I2C Address |
| LED | GPIO 2 | Output |
| Buzzer | GPIO 4 | Output |
| LDR | GPIO 34 | Analog Input (ADC) |

---

## Step 1: Prepare Arduino IDE

### 1.1 Add ESP32 Board Support
1. Open **Arduino IDE**
2. Go to **File → Preferences**
3. In "Additional Boards Manager URLs", paste:
   ```
   https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
   ```
4. Click **OK**
5. Go to **Tools → Board → Boards Manager**
6. Search for "ESP32" and install **esp32 by Espressif Systems**

### 1.2 Install Required Libraries
In Arduino IDE, go to **Sketch → Include Library → Manage Libraries** and install:
- **Adafruit VL53L0X** - ToF sensor support
- **LiquidCrystal I2C** - LCD display (by Frank de Brabander)
- Note: MPU6050 communication is via standard Wire library (included)

---

## Step 2: Configure & Upload Firmware

### 2.1 Configure Tuning Parameters (Optional)
Open **Cane_Firmware.ino** and adjust:
```cpp
int ldrThreshold = 700;      // LDR dark threshold (0-4095)
long fallThreshold = 20000;  // Acceleration threshold for fall detection
```

### 2.2 Select Board & Port
1. **Tools → Board → ESP32 Dev Module** (or your specific ESP32 variant)
2. **Tools → Port → COM#** (select your ESP32's USB port)
3. **Tools → Upload Speed → 921600** (for faster uploads)
4. **Tools → Flash Frequency → 80 MHz**

### 2.3 Upload Firmware
Click **Upload** (⬆️ button) or press **Ctrl+U**

### 2.4 Verify Installation
1. Open **Tools → Serial Monitor** (Ctrl+Shift+M)
2. Set baud rate to **115200**
3. Expect output similar to:
   ```
   SYSTEM STARTED
   L:<distance_cm>,T:<distance_mm>,LDR:<value>,F:<0|1>
   L:45,T:220,LDR:650,F:0
   L:42,T:215,LDR:648,F:0
   ```

---

## Step 3: Sensor Integration

### 3.1 TF-Luna LIDAR
- **Communication**: UART2 (115200 baud)
- **Output**: Distance in centimeters (cm)
- **Range**: 0.2m - 8m
- **Update Rate**: ~10 Hz

### 3.2 VL53L0X ToF
- **Communication**: I2C (0x29 default address)
- **Output**: Distance in millimeters (mm)
- **Range**: 0.05m - 1.2m (accurate for drop detection)
- **Purpose**: Downward-facing drop detection

### 3.3 MPU6050 Accelerometer
- **Communication**: I2C address 0x68
- **Detection**: Fall via total acceleration threshold
- **Threshold**: Configurable (default: 20000)
- **Priority**: Highest (triggers immediate buzzer)

### 3.4 LDR Light Sensor
- **Input**: Analog GPIO 34
- **Range**: 0-4095
- **Purpose**: Detect darkness and control LED indicator

---

## Step 4: Dashboard Integration

### 4.1 Install Python Dependencies
```bash
pip install -r requirements.txt
```

### 4.2 Data Format
The firmware outputs sensor data in CSV format on Serial:
```
L:<lidar_cm>,T:<tof_mm>,LDR:<value>,F:<fall_flag>
```

Example:
```
L:45,T:220,LDR:650,F:0
L:42,T:215,LDR:648,F:0
L:150,T:500,LDR:200,F:1  # Fall detected
```

### 4.3 Connect via Dashboard
1. Start Streamlit dashboard:
   ```bash
   streamlit run Project_Dashboard.py
   ```
2. Select **"Serial"** connection mode
3. Choose the appropriate USB port
4. Toggle **"Start stream"** ON

---

## Buzzer Logic

### Distance-Based Alerts
The buzzer triggers based on closest detected obstacle:

| Distance | Behavior |
|----------|----------|
| < 150 mm | Fast beep (150ms interval) |
| < 400 mm | Medium beep (400ms interval) |
| < 800 mm | Slow beep (800ms interval) |
| > 800 mm | Silent |

### Fall Detection
- **Highest Priority**: Fall detection via MPU6050 overrides distance-based alerts
- **Trigger**: Continuous buzzer tone on fall detection
- **Reset**: Buzzer resets when acceleration returns to normal

---

## Troubleshooting

### Serial Data Not Appearing
- **Check**: Correct USB port selected in Arduino IDE
- **Check**: Baud rate is 115200
- **Check**: All sensor connections secure
- **Fix**: Press ESP32 reset button

### TF-Luna Not Responding
- **Check**: UART2 connections (RX=16, TX=17)
- **Check**: TX/RX not swapped
- **Fix**: Reseat connections, verify 5V power supply

### VL53L0X Not Initializing
- **Check**: I2C pull-up resistors (if using long wires)
- **Check**: Address 0x29 not conflicting with LCD (0x27)
- **Fix**: Check Serial Monitor for "TOF FAIL" message

### MPU6050 Not Responding
- **Check**: I2C address 0x68 is correct
- **Check**: SDA/SCL pins (21/22) properly connected
- **Check**: 3.3V power supply to sensor
- **Fix**: Try MPU6050 address scanner sketch

### LCD Display Blank
- **Check**: I2C address is 0x27 (common default)
- **Check**: Backlight voltage (should be enabled in code)
- **Fix**: Upload display address finder sketch to identify actual address

---

## Performance Notes

- **Data Rate**: 10 Hz (100ms packets)
- **Latency**: Minimal (serial direct)
- **Accuracy**: 
  - LIDAR: ±3cm @ 1m
  - ToF: ±3mm @ 50cm
  - Accelerometer: ±2g range typical
- **Power Consumption**: ~500mA typical

---

## Next Steps

### Optional Enhancements
1. **Wireless Mode**: Upgrade to WiFi with WebSocket server
2. **Data Logging**: Add microSD card for offline data storage
3. **Cloud Integration**: Send alerts to cloud service
4. **Custom Alerts**: Implement vibration motor for discrete alerts

### Sensor Calibration
- Adjust `ldrThreshold` based on ambient light conditions
- Adjust `fallThreshold` based on user acceleration patterns

---

## Reference

- **Firmware File**: Cane_Firmware.ino
- **Data Format**: `L:<cm>,T:<mm>,LDR:<val>,F:<0|1>`
- **Serial Baud**: 115200
- **Dashboard Port**: 8501 (Streamlit default)

---

**Version**: Phase 2 - Dual Sensor with Fall Detection  
**Date**: May 2026  
**Branch**: `phase-2-changes` & `main`
