# Smart Cane WiFi Integration Setup Guide

## Overview
This guide covers how to set up the ESP32 with WiFi connectivity and connect it to the Streamlit dashboard wirelessly, eliminating the need for USB serial connections.

---

## Phase 2 Changes: WiFi Support

### New Files
- **Cane_Firmware_WiFi.ino** - WiFi-enabled ESP32 firmware with WebSocket server
- **WIFI_SETUP.md** - This setup guide

### Modified Files
- **Project_Dashboard.py** - Added WiFi connection mode and WebSocket client
- **requirements.txt** - Added `websocket-client` dependency

---

## Hardware Requirements
- ESP32 DevKit or similar board
- VL53L0X ToF sensor (distance)
- 16x2 I2C LCD display
- LDR (light sensor)
- LED and Buzzer
- WiFi network/router

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
- **Adafruit VL53L0X** (ToF sensor)
- **LiquidCrystal I2C** (by Frank de Brabander)
- **WebSocketsServer** (by Markus Sattler)

---

## Step 2: Upload Firmware to ESP32

### 2.1 Configure WiFi Credentials
Open **Cane_Firmware_WiFi.ino** in Arduino IDE and update:
```cpp
#define WIFI_SSID     "YOUR_SSID"        // Change this
#define WIFI_PASSWORD "YOUR_PASSWORD"    // Change this
```

### 2.2 Select Board & Port
1. **Tools → Board → ESP32 Dev Module** (or your specific board)
2. **Tools → Port → COM#** (select your ESP32's USB port)
3. **Tools → Upload Speed → 921600** (faster upload)

### 2.3 Upload
Click **Upload** (⬆️ icon) or press **Ctrl+U**

### 2.4 Verify Connection
Open **Tools → Serial Monitor** (Ctrl+Shift+M)
- Set baud rate to **115200**
- Look for output like:
  ```
  === SMART CANE FIRMWARE (WiFi) ===
  [WiFi] Connecting to: YOUR_SSID
  [WiFi] ✓ Connected!
  [WiFi] IP Address: 192.168.1.100
  [WS] Server started on port 81
  ```
- **Copy the IP address** (e.g., 192.168.1.100)

---

## Step 3: Update Dashboard Dependencies

### 3.1 Install Python Packages
```bash
pip install -r requirements.txt
```

Or install just the WiFi dependency:
```bash
pip install websocket-client
```

---

## Step 4: Run Dashboard with WiFi

### 4.1 Start Streamlit Dashboard
```bash
streamlit run Project_Dashboard.py
```

### 4.2 Configure Connection Mode
1. In the sidebar, select **"WiFi"** from "Connection Mode"
2. Enter the ESP32 IP address (from Serial Monitor step)
3. Toggle **"Start stream"** ON

You should see:
- ✓ Green success message: "✓ Connected to 192.168.1.100:81"
- Sensor data flowing in real-time
- No USB cable needed!

---

## Troubleshooting

### WiFi Won't Connect
- **Issue**: "WiFi FAILED" message on LCD
- **Fix**: 
  - Verify SSID and password in firmware (case-sensitive!)
  - Check if your WiFi password contains special characters (may need escaping)
  - Try closer to router
  - Reboot ESP32 and try again

### Dashboard Can't Connect
- **Issue**: "Could not connect to 192.168.1.100:81"
- **Fix**:
  - Verify ESP32 IP address matches Serial Monitor output
  - Ensure ESP32 is on same network as your computer
  - Check firewall allows WebSocket on port 81
  - Ping ESP32: `ping 192.168.1.100`

### WebSocket Port Already in Use
- **Issue**: Error about port 81 already bound
- **Fix**:
  - Find and kill process using port 81:
    ```bash
    netstat -ano | findstr :81
    taskkill /PID <PID> /F
    ```

### Sensor Data Not Updating
- **Issue**: Dashboard connected but no data flowing
- **Fix**:
  - Check Serial Monitor for "[DATA]" log messages
  - Verify WebSocket "Clients:" count > 0
  - Try reconnecting in sidebar
  - Restart ESP32

---

## Connection Modes

The dashboard now supports three connection modes:

### Mode 1: Serial
- Uses USB cable (original method)
- Good for development and debugging
- Full Serial Monitor visibility

### Mode 2: WiFi ⭐ (NEW)
- No USB cable required
- Real-time data via WebSocket
- Mobility around the space
- Requires matching SSID/password

### Mode 3: Mock
- Simulated data
- Perfect for testing dashboard UI
- No hardware needed

---

## Performance Notes

- **Data Rate**: 10 Hz (100ms packets) - same as serial
- **Latency**: ~50-100ms over local WiFi
- **Range**: Typically 30-50 meters from router
- **Bandwidth**: ~1-2 KB/s (very low)

---

## Next Steps

### Optional Enhancements
1. **Static IP**: Configure ESP32 with fixed IP in WiFi setup
2. **mDNS**: Access ESP32 by hostname instead of IP (e.g., `smartcane.local`)
3. **TLS/SSL**: Add HTTPS support for secure connection
4. **Data Logging**: Store WiFi sensor data to cloud

### Switching Back to Serial
Simply select **"Serial"** mode in the sidebar and choose the USB port.

---

## Reference

- **ESP32 PIN Layout**: See Cane_Firmware_WiFi.ino header
- **Data Protocol**: `dist_fwd,dist_drop,fall_flag,light_val` (matches dashboard parser)
- **WebSocket Format**: Plain text packets sent continuously
- **Dashboard Port**: 8501 (Streamlit default)
- **ESP32 WebSocket Port**: 81

---

## Support

For issues:
1. Check Serial Monitor output for detailed error messages
2. Verify WiFi credentials and network connectivity
3. Review troubleshooting section above
4. Check IP address format: should be `XXX.XXX.XXX.XXX`

---

**Version**: Phase 2 WiFi Integration  
**Date**: May 2026  
**Branch**: `phase-2-changes`
