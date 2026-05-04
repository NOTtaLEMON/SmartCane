/*
 * ============================================================================
 *  SMART CANE CLIP-ON  |  ESP32 FIRMWARE (WiFi Version)
 * ============================================================================
 *  Hardware:
 *    - 1x VL53L0X ToF (forward distance)
 *    - 16x2 LCD via I2C (LiquidCrystal_I2C @ 0x27)
 *    - LED         -> GPIO 2
 *    - Buzzer      -> GPIO 4
 *    - LDR (analog)-> GPIO 34
 *    - I2C SDA     -> GPIO 21
 *    - I2C SCL     -> GPIO 22
 *
 *  DATA PROTOCOL (matches dashboard parser):
 *      "dist_fwd,dist_drop,fall_flag,light_val"
 *      e.g. "045,000,0,0550"
 *
 *  LIBRARIES REQUIRED:
 *    - Adafruit VL53L0X
 *    - LiquidCrystal I2C (by Frank de Brabander)
 *    - WebSocketsServer (by Markus Sattler)
 *
 *  SETUP INSTRUCTIONS:
 *    1. Update WIFI_SSID and WIFI_PASSWORD below
 *    2. Select Board: ESP32 Dev Module
 *    3. Upload to ESP32
 *    4. Check Serial Monitor for IP address
 * ============================================================================
 */

#include <Wire.h>
#include <WiFi.h>
#include <WebSocketsServer.h>
#include <LiquidCrystal_I2C.h>
#include <Adafruit_VL53L0X.h>

// MPU6050 Register Definitions (no library needed)
#define MPU6050_ADDR 0x68
#define MPU6050_PWR_MGMT_1 0x6B
#define MPU6050_ACCEL_XOUT_H 0x3B
#define FALL_THRESHOLD 20000  // Acceleration threshold for fall detection

// ========== WiFi Configuration ==========
#define WIFI_SSID     "YOUR_SSID"        // Change this to your WiFi name
#define WIFI_PASSWORD "YOUR_PASSWORD"    // Change this to your WiFi password
#define WEBSOCKET_PORT 81

// ========== Pin Map ==========
#define LED_PIN     2
#define BUZZER_PIN  4
#define LDR_PIN     34
#define LIDAR_RX    16   // TF-Luna RX
#define LIDAR_TX    17   // TF-Luna TX

// ========== Tuning ==========
#define LDR_DARK_THRESHOLD  700
#define LOOP_MS             100

// ========== Objects ==========
LiquidCrystal_I2C lcd(0x27, 16, 2);
Adafruit_VL53L0X lox = Adafruit_VL53L0X();
WebSocketsServer webSocket(WEBSOCKET_PORT);

unsigned long lastTick = 0;
unsigned long lastIPDisplay = 0;
bool wifiConnected = false;
int connectedClients = 0;
String espIP = "";
int lidarDistance = 0;  // Distance in cm from TF-Luna
int fallDetected = 0;   // Fall flag (0 or 1)

// ========== Helper Functions ==========

// Read LIDAR distance from TF-Luna (via UART2)
void readLidarDistance() {
  if (Serial2.available() >= 9) {
    byte data[9];
    if (Serial2.read() == 0x59) {
      data[0] = 0x59;
      data[1] = Serial2.read();
      if (data[1] == 0x59) {
        for (int i = 2; i < 9; i++) {
          data[i] = Serial2.read();
        }
        lidarDistance = (data[2] | (data[3] << 8));
      }
    }
  }
}

// Initialize MPU6050
void initMPU6050() {
  Wire.beginTransmission(MPU6050_ADDR);
  Wire.write(MPU6050_PWR_MGMT_1);
  Wire.write(0);
  Wire.endTransmission(true);
  Serial.println("[MPU6050] Initialized");
}

// Read accelerometer and detect falls
void detectFall() {
  Wire.beginTransmission(MPU6050_ADDR);
  Wire.write(MPU6050_ACCEL_XOUT_H);
  Wire.endTransmission(false);
  Wire.requestFrom(MPU6050_ADDR, 6, true);
  
  int16_t accelX = (Wire.read() << 8) | Wire.read();
  int16_t accelY = (Wire.read() << 8) | Wire.read();
  int16_t accelZ = (Wire.read() << 8) | Wire.read();
  
  // Calculate total acceleration magnitude
  long accelMagnitude = (long)accelX * accelX + (long)accelY * accelY + (long)accelZ * accelZ;
  
  // If acceleration exceeds threshold, flag as fall
  fallDetected = (accelMagnitude > FALL_THRESHOLD) ? 1 : 0;
  
  if (fallDetected) {
    digitalWrite(BUZZER_PIN, HIGH);
    delay(100);
    digitalWrite(BUZZER_PIN, LOW);
  }
}

// ========== WebSocket Event Handler ==========
void webSocketEvent(uint8_t num, WStype_t type, uint8_t * payload, size_t length) {
  switch(type) {
    case WStype_CONNECTED: {
      Serial.printf("[WS] Client %u connected\n", num);
      connectedClients++;
      break;
    }
    case WStype_DISCONNECTED: {
      Serial.printf("[WS] Client %u disconnected\n", num);
      connectedClients--;
      break;
    }
    case WStype_TEXT:
    case WStype_BIN:
    default:
      break;
  }
}

// ========== Setup ==========
void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n\n=== SMART CANE FIRMWARE (WiFi) ===\n");

  // Initialize I2C
  Wire.begin(21, 22);
  
  // Initialize UART2 for TF-Luna LIDAR (115200 baud)
  Serial2.begin(115200, SERIAL_8N1, LIDAR_RX, LIDAR_TX);
  Serial.println("[LIDAR] UART2 initialized");
  
  // Initialize MPU6050
  initMPU6050();
  
  // Initialize GPIO
  pinMode(LED_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);

  // Initialize LCD
  lcd.init();
  lcd.backlight();
  lcd.print("Initializing...");
  Serial.println("[LCD] Initialized");

  // Initialize ToF sensor
  if (!lox.begin()) {
    Serial.println("[ERR] VL53L0X initialization failed!");
    lcd.clear();
    lcd.print("TOF FAIL");
    while(1);
  }
  Serial.println("[TOF] VL53L0X initialized");

  // Connect to WiFi
  Serial.print("[WiFi] Connecting to: ");
  Serial.println(WIFI_SSID);
  
  lcd.clear();
  lcd.print("WiFi Connecting");
  
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    wifiConnected = true;
    espIP = WiFi.localIP().toString();
    Serial.println("[WiFi] ✓ Connected!");
    Serial.print("[WiFi] IP Address: ");
    Serial.println(espIP);
    
    // Display IP on LCD (show last octet)
    lcd.clear();
    lcd.print("WiFi: OK");
    lcd.setCursor(0, 1);
    String ip = WiFi.localIP().toString();
    String lastOctet = ip.substring(ip.lastIndexOf('.')+1);
    lcd.print("IP:");
    lcd.print(lastOctet);
    
    // Start WebSocket server
    webSocket.begin();
    webSocket.onEvent(webSocketEvent);
    Serial.print("[WS] Server started on port ");
    Serial.println(WEBSOCKET_PORT);
  } else {
    wifiConnected = false;
    Serial.println("[WiFi] ✗ Connection failed!");
    lcd.clear();
    lcd.print("WiFi FAILED");
    lcd.setCursor(0, 1);
    lcd.print("Check SSID/Pass");
  }

  delay(2000);
}

// ========== Main Loop ==========
void loop() {
  // Handle WebSocket events
  webSocket.loop();

  // Check WiFi connection
  if (!wifiConnected && WiFi.status() == WL_CONNECTED) {
    wifiConnected = true;
    Serial.println("[WiFi] Re-connected!");
  } else if (wifiConnected && WiFi.status() != WL_CONNECTED) {
    wifiConnected = false;
    Serial.println("[WiFi] Disconnected!");
  }

  // Throttle main sensor loop
  if (millis() - lastTick < LOOP_MS) {
    delay(5);
    return;
  }
  lastTick = millis();

  // ---- Periodically display IP Address (every 10 seconds) ----
  if (millis() - lastIPDisplay >= 10000) {
    lastIPDisplay = millis();
    if (wifiConnected && espIP.length() > 0) {
      Serial.println("\n[IP_INFO] Current IP Address: " + espIP);
      Serial.println("[IP_INFO] WebSocket Port: 81");
      Serial.println("[IP_INFO] Connected Clients: " + String(connectedClients) + "\n");
    }
  }

  // ---- Read ToF Distance ----
  VL53L0X_RangingMeasurementData_t measure;
  lox.rangingTest(&measure, false);
  int distFwd = (measure.RangeStatus != 4) ? (int)measure.RangeMilliMeter : 0;

  // ---- Read LIDAR Distance (downward) ----
  readLidarDistance();

  // ---- Detect Falls (MPU6050) ----
  detectFall();

  // ---- Read Light Sensor (LDR) ----
  int ldrValue = analogRead(LDR_PIN);
  bool isDark = (ldrValue < LDR_DARK_THRESHOLD);

  // ---- LED Feedback (on when dark) ----
  digitalWrite(LED_PIN, isDark ? HIGH : LOW);

  // ---- Buzzer Feedback (distance alert) ----
  if (distFwd > 0 && distFwd < 100) {
    // Very close -- fast pulse
    digitalWrite(BUZZER_PIN, HIGH);
    delayMicroseconds(100000);
    digitalWrite(BUZZER_PIN, LOW);
  } else if (distFwd > 0 && distFwd < 300) {
    // Approaching -- slower pulse
    digitalWrite(BUZZER_PIN, HIGH);
    delayMicroseconds(300000);
    digitalWrite(BUZZER_PIN, LOW);
  } else {
    digitalWrite(BUZZER_PIN, LOW);
  }

  // ---- Update LCD Display ----
  lcd.clear();
  lcd.setCursor(0, 0);
  
  if (measure.RangeStatus != 4) {
    lcd.print("D:");
    lcd.print(distFwd);
    lcd.print("mm");
  } else {
    lcd.print("Out of range");
  }
  
  lcd.setCursor(0, 1);
  lcd.print("L:");
  lcd.print(ldrValue);
  lcd.print(" W:");
  lcd.print(wifiConnected ? "ON" : "OFF");

  // ---- Prepare sensor packet (format: dist_fwd,dist_drop,fall_flag,light_val) ----
  char buf[64];
  snprintf(buf, sizeof(buf), "%03d,%03d,%d,%04d", distFwd, lidarDistance, fallDetected, ldrValue);

  // ---- Broadcast via WebSocket to all connected clients ----
  if (wifiConnected && connectedClients > 0) {
    webSocket.broadcastTXT((uint8_t*)buf, strlen(buf));
  }

  // ---- Also send to Serial Monitor for debugging ----
  Serial.print("[DATA] ");
  Serial.print(buf);
  Serial.print(" | WiFi:");
  Serial.print(wifiConnected ? "ON" : "OFF");
  Serial.print(" | Clients:");
  Serial.println(connectedClients);
}
