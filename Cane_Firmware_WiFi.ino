// === VERSION: v3.4 - STABILIZED LIVE PRODUCTION BUILD ===
// === If you see this, you have the latest firmware ===
/*
 * ============================================================================
 *  SMART CANE | ESP32 FIRMWARE (WiFi Version)
 * ============================================================================
 *  Hardware:
 *    - TF-Luna LiDAR (forward, UART2) -> RX:16 TX:17
 *    - VL53L0X ToF  (drop detect, I2C)
 *    - MPU6050      (fall detect, I2C)
 *    - 16x2 LCD     (I2C @ 0x27)
 *    - LED          -> GPIO 2
 *    - Buzzer       -> GPIO 4
 *    - I2C SDA      -> GPIO 21
 *    - I2C SCL      -> GPIO 22
 *
 *  BUZZER PRIORITY:
 *    1. Fall alert  (MPU6050) — 5 s continuous
 *    2. LiDAR zones (0-50 cm fast / 51-100 cm medium / 101-150 cm slow)
 *    3. ToF drop    (> 250 mm when path is clear)
 *
 *  DATA PROTOCOL:
 *    "dist_fwd,dist_drop,fall_flag"   e.g. "045,180,0"
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
#include <math.h>

// ================= MPU6050 =================
#define MPU6050_ADDR         0x68
#define MPU6050_PWR_MGMT_1   0x6B
#define MPU6050_ACCEL_XOUT_H 0x3B
#define FALL_THRESHOLD       49512   // Filters heavy sidewalk taps entirely

// ================= TOF THRESHOLD ===========
#define TOF_DROP_THRESHOLD   250     // 25 cm (250 mm) for deep drop warning zones

// ================= WIFI ====================
#define WIFI_SSID      "ARAVIND"     // *** replace with actual SSID ***
#define WIFI_PASSWORD  "Akila123"    // *** replace with actual password ***
#define WEBSOCKET_PORT 81

// ================= PINS ====================
#define LED_PIN    2
#define BUZZER_PIN 4
#define LIDAR_RX   16
#define LIDAR_TX   17

// ================= SETTINGS =================
#define LOOP_MS 80

// ================= OBJECTS ==================
LiquidCrystal_I2C lcd(0x27, 16, 2);
Adafruit_VL53L0X  lox = Adafruit_VL53L0X();
WebSocketsServer  webSocket(WEBSOCKET_PORT);

// ================= VARIABLES =================
unsigned long lastTick      = 0;
unsigned long lastIPDisplay = 0;
unsigned long lastWifiRetry = 0;
unsigned long lastLCDUpdate = 0;
unsigned long fallStartTime = 0;

bool wifiConnected   = false;
bool fallAlertActive = false;

int connectedClients = 0;
String espIP         = "";

int lidarDistance = 0;
int fallDetected  = 0;

// ======================================================
// TF-LUNA READ
// ======================================================
void readLidarDistance() {
  while (Serial2.available() >= 9) {
    if (Serial2.read() == 0x59) {
      if (Serial2.read() == 0x59) {
        byte data[7];
        for (int i = 0; i < 7; i++) data[i] = Serial2.read();
        lidarDistance = data[0] + (data[1] << 8);
      }
    }
  }
}

// ======================================================
// MPU INIT
// ======================================================
void initMPU6050() {
  Wire.beginTransmission(MPU6050_ADDR);
  Wire.write(MPU6050_PWR_MGMT_1);
  Wire.write(0);
  Wire.endTransmission(true);
  Serial.println("[MPU] Initialized");
}

// ======================================================
// FALL DETECTION  (sqrt magnitude, latching 5-second alert)
// ======================================================
void detectFall() {
  Wire.beginTransmission(MPU6050_ADDR);
  Wire.write(MPU6050_ACCEL_XOUT_H);
  Wire.endTransmission(false);
  Wire.requestFrom(MPU6050_ADDR, 6, true);

  int16_t accelX = (Wire.read() << 8) | Wire.read();
  int16_t accelY = (Wire.read() << 8) | Wire.read();
  int16_t accelZ = (Wire.read() << 8) | Wire.read();

  float magnitude = sqrt(
    (float)accelX * accelX +
    (float)accelY * accelY +
    (float)accelZ * accelZ
  );

  if (magnitude > FALL_THRESHOLD && !fallAlertActive) {
    fallDetected    = 1;
    fallAlertActive = true;
    fallStartTime   = millis();
    Serial.println("[FALL] DETECTED");
  }
}

// ======================================================
// WEBSOCKET EVENT
// ======================================================
void webSocketEvent(uint8_t num, WStype_t type, uint8_t* payload, size_t length) {
  switch (type) {
    case WStype_CONNECTED:
      Serial.printf("[WS] Client %u connected\n", num);
      connectedClients++;
      break;
    case WStype_DISCONNECTED:
      Serial.printf("[WS] Client %u disconnected\n", num);
      if (connectedClients > 0) connectedClients--;
      break;
    default:
      break;
  }
}

// ======================================================
// SETUP
// ======================================================
void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n\n=== SMART CANE FIRMWARE (WiFi) ===");
  Serial.println("=== VERSION: v3.4 - STABILIZED LIVE PRODUCTION BUILD ===\n");

  // I2C
  Wire.begin(21, 22);
  Wire.setClock(100000);
  delay(200);

  // TF-Luna UART
  Serial2.begin(115200, SERIAL_8N1, LIDAR_RX, LIDAR_TX);
  Serial.println("[LIDAR] UART2 initialized");

  // MPU6050
  initMPU6050();

  // GPIO
  pinMode(LED_PIN,    OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);

  // LCD
  lcd.init();
  lcd.backlight();
  lcd.print("Initializing...");
  Serial.println("[LCD] Initialized");

  // ToF (5 attempts)
  bool tof_ok = false;
  for (int i = 0; i < 5; i++) {
    if (lox.begin()) { tof_ok = true; break; }
    delay(300);
  }
  if (!tof_ok) {
    Serial.println("[ERR] VL53L0X init failed!");
    lcd.clear(); lcd.print("TOF FAIL");
    while (1);
  }
  Serial.println("[TOF] VL53L0X initialized");

  // WiFi
  Serial.print("[WiFi] Connecting to: ");
  Serial.println(WIFI_SSID);
  lcd.clear(); lcd.print("WiFi Connecting");

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 40) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    wifiConnected = true;
    espIP = WiFi.localIP().toString();
    Serial.println("[WiFi] Connected!");
    Serial.println("[WiFi] IP: " + espIP);

    lcd.clear();
    lcd.print("WiFi: OK");
    lcd.setCursor(0, 1);
    String lastOctet = espIP.substring(espIP.lastIndexOf('.') + 1);
    lcd.print("IP:"); lcd.print(lastOctet);

    webSocket.begin();
    webSocket.onEvent(webSocketEvent);
    Serial.println("[WS] Server started on port " + String(WEBSOCKET_PORT));
  } else {
    wifiConnected = false;
    Serial.println("[WiFi] Connection failed!");
    lcd.clear(); lcd.print("WiFi FAILED");
    lcd.setCursor(0, 1); lcd.print("Check SSID/Pass");
  }

  delay(2000);
}

// ======================================================
// MAIN LOOP
// ======================================================
void loop() {
  webSocket.loop();

  // ---- WiFi connection management ----
  if (!wifiConnected && WiFi.status() == WL_CONNECTED) {
    wifiConnected = true;
    espIP = WiFi.localIP().toString();
    webSocket.begin();
    webSocket.onEvent(webSocketEvent);
    Serial.println("[WiFi] Re-connected! IP: " + espIP);
  } else if (wifiConnected && WiFi.status() != WL_CONNECTED) {
    wifiConnected    = false;
    connectedClients = 0;
    Serial.println("[WiFi] Disconnected!");
  } else if (!wifiConnected && (millis() - lastWifiRetry > 30000)) {
    lastWifiRetry = millis();
    Serial.println("[WiFi] Retrying...");
    WiFi.disconnect();
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  }

  // ---- Throttle sensor loop ----
  if (millis() - lastTick < LOOP_MS) return;
  lastTick = millis();

  // ---- Periodic IP display (every 10 s) ----
  if (millis() - lastIPDisplay >= 10000) {
    lastIPDisplay = millis();
    if (wifiConnected && espIP.length() > 0) {
      Serial.println("\n[IP_INFO] IP: " + espIP);
      Serial.println("[IP_INFO] WS Port: 81");
      Serial.println("[IP_INFO] Clients: " + String(connectedClients) + "\n");
    }
  }

  // ---- ToF (drop sensor) ----
  VL53L0X_RangingMeasurementData_t measure;
  lox.rangingTest(&measure, false);
  int distDrop = (measure.RangeStatus != 4) ? (int)measure.RangeMilliMeter : 0;

  // ---- TF-Luna (forward navigation) ----
  readLidarDistance();
  int distForward = lidarDistance;

  // ---- MPU fall detection ----
  detectFall();

  // ---- LED: on during fall alert ----
  digitalWrite(LED_PIN, fallAlertActive ? HIGH : LOW);

  // ==================================================
  // BUZZER LOGIC
  // Priority: 1 Fall  2 LiDAR zones  3 ToF drop
  // ==================================================

  if (fallAlertActive) {
    // ---- PRIORITY 1: Fall — continuous buzz for 5 s ----
    digitalWrite(BUZZER_PIN, HIGH);
    if (millis() - fallStartTime >= 5000) {
      fallAlertActive = false;
      fallDetected    = 0;
      digitalWrite(BUZZER_PIN, LOW);
    }
  } else {
    digitalWrite(BUZZER_PIN, LOW);

    if (distForward > 0 && distForward <= 50) {
      // ---- PRIORITY 2a: 0–50 cm — fast beep ----
      digitalWrite(BUZZER_PIN, HIGH); delay(100);
      digitalWrite(BUZZER_PIN, LOW);  delay(100);

    } else if (distForward > 50 && distForward <= 100) {
      // ---- PRIORITY 2b: 51–100 cm — medium beep ----
      digitalWrite(BUZZER_PIN, HIGH); delay(120);
      digitalWrite(BUZZER_PIN, LOW);  delay(200);

    } else if (distForward > 100 && distForward <= 150) {
      // ---- PRIORITY 2c: 101–150 cm — slow beep ----
      digitalWrite(BUZZER_PIN, HIGH); delay(150);
      digitalWrite(BUZZER_PIN, LOW);  delay(400);

    } else if ((distForward == 0 || distForward > 150) && distDrop > TOF_DROP_THRESHOLD) {
      // ---- PRIORITY 3: Drop detected using 250mm ceiling logic (path clear) ----
      digitalWrite(BUZZER_PIN, HIGH); delay(350);
      digitalWrite(BUZZER_PIN, LOW);  delay(450);
    }
    // else: SAFE — buzzer stays LOW
  }

  // ---- LCD (every 400 ms) ----
  if (millis() - lastLCDUpdate > 400) {
    lastLCDUpdate = millis();
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("F:"); lcd.print(distForward);
    lcd.print(" D:"); lcd.print(distDrop);
    lcd.setCursor(0, 1);
    lcd.print(fallAlertActive ? "FALL! " : "SAFE  ");
    lcd.print(wifiConnected ? "W:ON" : "W:OFF");
  }

  // ---- Packet: "dist_fwd,dist_drop,fall_flag" ----
  char buf[32];
  snprintf(buf, sizeof(buf), "%03d,%03d,%d", distForward, distDrop, fallDetected);

  if (wifiConnected) {
    webSocket.broadcastTXT((uint8_t*)buf, strlen(buf));
  }

  // ---- Serial debug ----
  Serial.print("[DATA] "); Serial.print(buf);
  Serial.print(" | WiFi:"); Serial.print(wifiConnected ? "ON" : "OFF");
  Serial.print(" | Clients:"); Serial.println(connectedClients);
}
