# ESP32 WiFi Dashboard Connection Guide

A complete step-by-step process to connect your ESP32-based Smart Cane with the WiFi dashboard for real-time sensor data streaming.

---

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Phase 1: Hardware Setup](#phase-1-hardware-setup)
3. [Phase 2: Arduino IDE Configuration](#phase-2-arduino-ide-configuration)
4. [Phase 3: Upload Firmware to ESP32](#phase-3-upload-firmware-to-esp32)
5. [Phase 4: Obtain ESP32 IP Address](#phase-4-obtain-esp32-ip-address)
6. [Phase 5: Configure Dashboard](#phase-5-configure-dashboard)
7. [Phase 6: Connect Dashboard to ESP32](#phase-6-connect-dashboard-to-esp32)
8. [Phase 7: Verify Connection](#phase-7-verify-connection)
9. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Hardware
- **ESP32 Dev Module** (or compatible ESP32 board)
- **USB Cable** (USB-A to Micro-USB or USB-C, depending on your ESP32)
- **WiFi Network** (2.4 GHz WiFi router - ESP32 doesn't support 5 GHz)
- **VL53L0X ToF Sensor** (Time-of-Flight distance sensor)
- **16x2 I2C LCD Display**
- **LED** and **Buzzer** (for feedback)
- **LDR Sensor** (Light-dependent resistor)

### Required Software
- **Arduino IDE** (v1.8.13 or newer)
- **Python 3.8+** (for running the dashboard)
- **Git** (optional, for cloning/version control)

### Network Requirements
- WiFi credentials (SSID and password) for your 2.4 GHz network
- Ability to note the ESP32's IP address on the network

---

## Phase 1: Hardware Setup

### Step 1.1: Verify Pin Connections

Ensure all sensors are properly connected to the ESP32 with the following pin assignments:

| Component | ESP32 Pin | Details |
|-----------|-----------|---------|
| **I2C SDA** (VL53L0X, LCD) | GPIO 21 | Data line |
| **I2C SCL** (VL53L0X, LCD) | GPIO 22 | Clock line |
| **LED** | GPIO 2 | Light indicator |
| **Buzzer** | GPIO 4 | Audio alert |
| **LDR (Analog)** | GPIO 34 | Light detection |

### Step 1.2: Power Connection
- Connect **USB cable** to ESP32's Micro-USB (or USB-C) port
- This provides both power and communication for programming
- Alternatively, use an external 5V power supply if required

### Step 1.3: Verify Hardware
- LED should illuminate when powered
- Check that I2C devices (ToF sensor and LCD) are properly wired
- Ensure no loose connections

---

## Phase 2: Arduino IDE Configuration

### Step 2.1: Install Arduino IDE
1. Download from [arduino.cc](https://www.arduino.cc/en/software)
2. Install following the on-screen instructions
3. Launch Arduino IDE

### Step 2.2: Add ESP32 Board Support
1. Open **File → Preferences** (or **Arduino → Preferences** on macOS)
2. Locate the **"Additional Boards Manager URLs"** field
3. Paste the following URL:
   ```
   https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
   ```
4. Click **OK**

### Step 2.3: Install ESP32 Board Package
1. Go to **Tools → Board → Boards Manager**
2. Search for: `ESP32`
3. Select **"esp32 by Espressif Systems"** (version 2.0.0 or higher recommended)
4. Click **Install**
5. Wait for installation to complete (~2-3 minutes)

### Step 2.4: Install Required Libraries
1. Go to **Tools → Manage Libraries**
2. Install these libraries one by one:
   - **"Adafruit VL53L0X"** by Adafruit
   - **"LiquidCrystal I2C"** by Frank de Brabander
   - **"WebSocketsServer"** by Markus Sattler (version 2.4.0 or higher)

   For each:
   - Search the library name
   - Select it from the results
   - Click **Install**
   - Wait for completion

3. Verify installation: **Sketch → Include Library** should list all three libraries

---

## Phase 3: Upload Firmware to ESP32

### Step 3.1: Open the WiFi Firmware
1. In Arduino IDE, open: **File → Open**
2. Navigate to your SmartCane project folder
3. Select: **Cane_Firmware_WiFi.ino**
4. The file will open in the Arduino IDE

### Step 3.2: Configure WiFi Credentials
1. Locate lines 35-36 in the code:
   ```cpp
   #define WIFI_SSID     "YOUR_SSID"        // Change this to your WiFi name
   #define WIFI_PASSWORD "YOUR_PASSWORD"    // Change this to your WiFi password
   ```

2. Replace:
   - `"YOUR_SSID"` → Your actual WiFi network name (keep the quotes)
   - `"YOUR_PASSWORD"` → Your actual WiFi password (keep the quotes)

   Example:
   ```cpp
   #define WIFI_SSID     "HomeNetwork"
   #define WIFI_PASSWORD "mySecurePassword123"
   ```

3. **Important:** Do NOT commit this file to public repositories (credentials are exposed)

### Step 3.3: Select Board and Port
1. **Select Board:**
   - Go to **Tools → Board → ESP32 Arduino**
   - Choose: **"ESP32 Dev Module"** (or your specific ESP32 variant)

2. **Select COM Port:**
   - Go to **Tools → Port**
   - Select the COM port where your ESP32 is connected
   - On Windows: typically `COM3`, `COM4`, `COM5`, etc.
   - On macOS: typically `/dev/cu.SLAB_USBtoUART` or similar
   - On Linux: typically `/dev/ttyUSB0`
   
   **Tip:** If unsure, disconnect ESP32, note available ports, reconnect, and see which new port appears.

3. **Verify Other Settings:**
   - **Upload Speed:** 115200
   - **Flash Frequency:** 80 MHz
   - **Flash Mode:** DIO

### Step 3.4: Upload Firmware
1. Click the **Upload** button (→ icon in toolbar) or press **Ctrl+U**
2. Watch the bottom status bar for upload progress
3. You'll see:
   ```
   Connecting......................
   Uploading....
   ```
4. Wait for completion (typically 30-60 seconds)
5. When done, you'll see:
   ```
   Hard resetting via RTS pin...
   ```

### Step 3.5: Verify Upload Success
- The console should show no errors (lines starting with "error" in red)
- If successful, the LED on your ESP32 will blink
- The LCD display should show startup messages

---

## Phase 4: Obtain ESP32 IP Address

### Step 4.1: Open Serial Monitor
1. In Arduino IDE, click **Tools → Serial Monitor** (or press **Ctrl+Shift+M**)
2. In the bottom-right, set baud rate to: **115200**
3. The Serial Monitor should now display boot messages

### Step 4.2: Locate the IP Address
Watch the serial monitor output. You should see:
```
=== SMART CANE FIRMWARE (WiFi) ===

[WiFi] Connecting to: HomeNetwork
.................
[WiFi] ✓ Connected!
[WiFi] IP Address: 192.168.1.100
[WS] Server started on port 81
```

**Copy the IP Address** (in this example: `192.168.1.100`)

### Step 4.3: What If WiFi Doesn't Connect?
If you see:
```
[WiFi] ✗ Connection failed!
Check SSID/Pass
```

Then:
1. Double-check WiFi SSID and password in the firmware (Phase 3.2)
2. Verify the WiFi network is 2.4 GHz (not 5 GHz)
3. Ensure the ESP32 is in range of the router
4. See [Troubleshooting](#troubleshooting) section below

---

## Phase 5: Configure Dashboard

### Step 5.1: Install Python Dependencies
1. Open a terminal/command prompt in your SmartCane project folder
2. Run:
   ```bash
   pip install -r requirements.txt
   ```
   
   This installs:
   - **streamlit** – Dashboard framework
   - **websocket-client** – WiFi communication with ESP32
   - **opencv-python** – Vision processing
   - **pandas** – Data handling
   - Other dependencies

3. Wait for all packages to install successfully

### Step 5.2: Verify Installation
Run:
```bash
python -c "import streamlit; import websocket; print('✓ Dependencies OK')"
```

If successful, you'll see: `✓ Dependencies OK`

---

## Phase 6: Connect Dashboard to ESP32

### Step 6.1: Launch the Dashboard
1. In your terminal (in the SmartCane project folder), run:
   ```bash
   streamlit run Project_Dashboard.py
   ```

2. Wait for startup (20-30 seconds first time)
3. A browser window will automatically open with the dashboard
4. You'll see something like:
   ```
   Local URL: http://localhost:8501
   Network URL: http://192.168.x.x:8501
   ```

### Step 6.2: Select WiFi Mode
1. On the left sidebar, find the **"Connection Mode"** dropdown
2. Select: **"WiFi"**
3. A new input field appears asking for the **ESP32 IP Address**

### Step 6.3: Enter ESP32 IP Address
1. Paste the IP address you obtained in [Phase 4.2](#step-42-locate-the-ip-address)
   (Example: `192.168.1.100`)
2. Press **Enter** or click outside the field
3. The dashboard will attempt to connect to the WebSocket server on the ESP32

---

## Phase 7: Verify Connection

### Step 7.1: Check Connection Status
1. Look at the dashboard for a **"Status"** indicator (usually at the top)
2. It should show: **"✓ Connected"** in green

### Step 7.2: Verify Sensor Data
Once connected, you should see live updates:
- **Distance (mm):** Forward obstacle distance from VL53L0X
- **Light Level:** LDR sensor value (0-4095)
- **Status Messages:** WiFi connection info
- **Real-time Graphs:** Distance and light level trends

### Step 7.3: Test Feedback
1. **Move your hand** in front of the ToF sensor – distance should decrease
2. **Cover the LDR** – light level should decrease, LED should turn on
3. **Listen for buzzer** – beeps when obstacles are detected

If all data updates in real-time, your connection is working!

---

## Troubleshooting

### Problem: "WiFi Connection Failed" on ESP32

**Symptom:**
```
[WiFi] ✗ Connection failed!
Check SSID/Pass
```

**Solutions:**
1. **Verify WiFi Credentials:**
   - Check that SSID and password are correct
   - Ensure no extra spaces in the WiFi name or password
   - WiFi name is case-sensitive

2. **Check Network Compatibility:**
   - ESP32 only supports 2.4 GHz WiFi (not 5 GHz)
   - If your router broadcasts both bands, ensure it's connecting to 2.4 GHz
   - Check router settings or use a separate 2.4 GHz network

3. **Verify Signal Strength:**
   - Bring ESP32 closer to the router
   - Ensure line of sight (or minimal obstacles)

4. **Restart ESP32:**
   - Disconnect USB
   - Wait 5 seconds
   - Reconnect USB
   - Watch Serial Monitor for connection attempt

---

### Problem: Dashboard Can't Connect to ESP32

**Symptom:**
```
Connection Failed: [Errno -2] Name or service not known
```
or no connection indication on dashboard

**Solutions:**
1. **Verify IP Address:**
   - Confirm the IP address is correct (check Serial Monitor again)
   - Ping the IP: `ping 192.168.1.100` (Windows/Mac/Linux)
   - If ping fails, ESP32 is not reachable

2. **Check Network Connection:**
   - Ensure your computer is on the same WiFi network as the ESP32
   - If using separate networks, they must be on the same subnet

3. **Verify WebSocket Port:**
   - Firmware uses port **81** for WebSocket (line 40 in Cane_Firmware_WiFi.ino)
   - Dashboard should auto-detect this
   - If custom port is needed, update both firmware and dashboard code

4. **Restart Both Devices:**
   - Restart ESP32 (disconnect/reconnect USB)
   - Restart the dashboard (press `Ctrl+C` in terminal, run `streamlit run Project_Dashboard.py` again)

---

### Problem: Sensor Data Not Updating

**Symptom:**
```
Connected, but no sensor readings appear
```

**Solutions:**
1. **Check Sensor Connections:**
   - Verify all I2C connections (SDA/SCL) are tight
   - LCD should display "WiFi: OK" after boot
   - If LCD shows "TOF FAIL", sensor isn't detected

2. **Verify I2C Addresses:**
   - Default: VL53L0X at `0x29`, LCD at `0x27`
   - If different, firmware must be updated accordingly (line 40, 53)

3. **Check Data Format:**
   - Firmware sends: `"dist_fwd,dist_drop,fall_flag,light_val"`
   - Example: `"045,000,0,0550"`
   - Dashboard expects this exact format

4. **Check Serial Monitor:**
   - While connected via WiFi, Serial Monitor should still show debug output
   - Look for lines like: `[DATA] Sending: 045,000,0,0550`

---

### Problem: Port Not Found / Upload Fails

**Symptom:**
```
Failed to open COM port
```
or
```
Port menu shows no devices
```

**Solutions:**
1. **Install USB Driver:**
   - Many ESP32 boards use CH340 or CP2102 USB chips
   - Windows: Download and install [CH340 driver](https://sparks.gogo.co.nz/ch340.html)
   - macOS/Linux: Usually automatic

2. **Check USB Cable:**
   - Use a proper **data cable** (not just charging cable)
   - Try a different USB port
   - Test cable with another device

3. **Restart Arduino IDE and ESP32:**
   - Close Arduino IDE completely
   - Disconnect ESP32
   - Restart computer
   - Reconnect ESP32
   - Open Arduino IDE

---

### Problem: Serial Monitor Shows Garbage Characters

**Symptom:**
```
þÿÿþþþþþþþþÉ[0m...
```

**Solutions:**
1. **Check Baud Rate:**
   - Bottom-right of Serial Monitor should show **115200**
   - If not, click dropdown and select **115200**

2. **Restart Serial Monitor:**
   - Close Serial Monitor (click X)
   - Wait 2 seconds
   - Open again (**Tools → Serial Monitor**)

---

### Problem: Dashboard Shows "Connection Refused"

**Symptom:**
```
[Errno 111] Connection refused
```

**Solutions:**
1. **Check WebSocket Server:**
   - Serial Monitor should show: `[WS] Server started on port 81`
   - If not, there was an error during WiFi connection

2. **Verify Firewall:**
   - Windows Firewall might block port 81
   - Try: **Settings → Firewall → Allow app through firewall**
   - Add Python or Arduino IDE to allowed list

3. **Manual Port Test (Advanced):**
   - Open terminal and run:
     ```bash
     telnet 192.168.1.100 81
     ```
   - If it connects, port is open; if not, firewall is blocking

---

## Quick Reference Summary

| Step | Action | Expected Result |
|------|--------|-----------------|
| **1** | Wire sensors to ESP32 | All connections secure |
| **2** | Configure Arduino IDE for ESP32 | Board "ESP32 Dev Module" available |
| **3** | Edit WiFi credentials | Lines 35-36 show your SSID/password |
| **4** | Upload firmware | Serial Monitor shows `[WiFi] IP Address: xxx.xxx.xxx.xxx` |
| **5** | Note ESP32 IP | Copy IP address (e.g., `192.168.1.100`) |
| **6** | Install Python dependencies | `pip install -r requirements.txt` succeeds |
| **7** | Launch dashboard | Browser opens to `http://localhost:8501` |
| **8** | Select WiFi mode | Dashboard shows WiFi connection options |
| **9** | Enter ESP32 IP | Dashboard shows `✓ Connected` |
| **10** | Test sensors | Distance/Light values update in real-time |

---

## Additional Resources

- [ESP32 Official Documentation](https://docs.espressif.com/projects/esp32-rtos-sdk/en/latest/)
- [Arduino IDE User Guide](https://docs.arduino.cc/software/ide/userguide)
- [Streamlit Documentation](https://docs.streamlit.io/)
- [WebSocket Protocol](https://tools.ietf.org/html/rfc6455)

---

## Support & Debugging

If you encounter issues not covered above:

1. **Check Serial Monitor Output:**
   - Most errors are logged here
   - Look for `[ERR]`, `[WARN]`, or error codes

2. **Enable Verbose Output (Advanced):**
   - In Arduino IDE: **File → Preferences → Show verbose output during upload** ✓
   - Re-upload firmware to see detailed messages

3. **Test Connectivity:**
   ```bash
   ping <ESP32_IP>
   curl http://<ESP32_IP>:81
   ```

4. **Restart Everything:**
   - Close Arduino IDE
   - Close Dashboard
   - Power off ESP32
   - Wait 10 seconds
   - Power on and restart in order: Arduino IDE → ESP32 → Dashboard

---

## Success Checklist

- [ ] ESP32 connected to WiFi (Serial Monitor shows IP)
- [ ] Dashboard launched successfully (browser opens)
- [ ] Dashboard shows "WiFi Connected" status
- [ ] Sensor data updates in real-time
- [ ] Moving hand in front of sensor changes distance reading
- [ ] Covering LDR changes light value and turns on LED
- [ ] Buzzer sounds when obstacle is detected

**Once all items are checked, your ESP32 WiFi dashboard is ready to use!** 🎉

---

**Last Updated:** May 2026  
**Firmware Version:** WiFi v1.0  
**Dashboard Version:** Phase 2
