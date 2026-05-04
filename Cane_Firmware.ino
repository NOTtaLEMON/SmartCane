#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <Adafruit_VL53L0X.h>

// ===== TF-LUNA =====
HardwareSerial TFSerial(2);

// ===== TOF =====
Adafruit_VL53L0X lox = Adafruit_VL53L0X();

// ===== LCD =====
LiquidCrystal_I2C lcd(0x27, 16, 2);

// ===== PINS =====
#define BUZZER_PIN 4
#define LDR_PIN 34
#define LED_PIN 2

// ===== VARIABLES =====
int lidarDist = -1;   // cm
int tofDist = -1;     // mm

unsigned long lastPrint = 0;
unsigned long lastBeep = 0;
bool buzzerState = false;

int ldrThreshold = 700;
long fallThreshold = 20000;

// ===== MPU =====
int16_t ax, ay, az;
long totalAccel = 0;

void setup() {
  Serial.begin(115200);
  delay(500);

  Serial.println("SYSTEM STARTED");

  // TF-Luna (UART2)
  TFSerial.begin(115200, SERIAL_8N1, 16, 17);

  // TOF (I2C)
  Wire.begin(21, 22);
  if (!lox.begin()) {
    Serial.println("TOF FAIL");
    while (1);
  }

  // MPU6050 wake
  Wire.beginTransmission(0x68);
  Wire.write(0x6B);
  Wire.write(0);
  Wire.endTransmission();

  // LCD
  lcd.init();
  lcd.backlight();

  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(LED_PIN, OUTPUT);
}

void loop() {

  // ===== TF-LUNA (FAST READ) =====
  while (TFSerial.available() >= 9) {
    if (TFSerial.read() == 0x59 && TFSerial.read() == 0x59) {
      lidarDist = TFSerial.read() + TFSerial.read() * 256;
      for (int i = 0; i < 5; i++) TFSerial.read();
    }
  }

  // ===== TOF =====
  VL53L0X_RangingMeasurementData_t measure;
  lox.rangingTest(&measure, false);

  if (measure.RangeStatus != 4) {
    tofDist = measure.RangeMilliMeter;
  }

  // ===== LDR =====
  int ldrValue = analogRead(LDR_PIN);
  bool isDark = (ldrValue < ldrThreshold);
  digitalWrite(LED_PIN, isDark ? HIGH : LOW);

  // ===== MPU =====
  Wire.beginTransmission(0x68);
  Wire.write(0x3B);
  Wire.endTransmission(false);
  Wire.requestFrom(0x68, 6, true);

  ax = Wire.read() << 8 | Wire.read();
  ay = Wire.read() << 8 | Wire.read();
  az = Wire.read() << 8 | Wire.read();

  totalAccel = abs(ax) + abs(ay) + abs(az);
  bool fallDetected = (totalAccel > fallThreshold);

  // ===== BUZZER =====
  unsigned long now = millis();
  bool buzzerOutput = false;

  int closestDist = 10000;

  if (lidarDist > 0) {
    int lidar_mm = lidarDist * 10;
    if (lidar_mm < closestDist) closestDist = lidar_mm;
  }

  if (tofDist > 0 && tofDist < closestDist) {
    closestDist = tofDist;
  }

  // FALL → highest priority
  if (fallDetected) {
    buzzerOutput = true;
  }
  else {
    if (closestDist < 150) {
      if (now - lastBeep > 150) {
        buzzerState = !buzzerState;
        lastBeep = now;
      }
      buzzerOutput = buzzerState;
    }
    else if (closestDist < 400) {
      if (now - lastBeep > 400) {
        buzzerState = !buzzerState;
        lastBeep = now;
      }
      buzzerOutput = buzzerState;
    }
    else if (closestDist < 800) {
      if (now - lastBeep > 800) {
        buzzerState = !buzzerState;
        lastBeep = now;
      }
      buzzerOutput = buzzerState;
    }
    else {
      buzzerOutput = false;
    }
  }

  digitalWrite(BUZZER_PIN, buzzerOutput);

  // ===== LCD =====
  lcd.setCursor(0, 0);
  lcd.print("L:");
  lcd.print(lidarDist);
  lcd.print(" T:");
  lcd.print(tofDist);
  lcd.print("   ");

  lcd.setCursor(0, 1);
  if (fallDetected) lcd.print("FALL ");
  else lcd.print("OK   ");

  lcd.print(isDark ? "DARK " : "BRIGHT");

  // ===== SERIAL OUTPUT (STREAMLIT FORMAT) =====
  if (now - lastPrint > 100) {

    Serial.print("L:");
    Serial.print(lidarDist);     // cm

    Serial.print(",T:");
    Serial.print(tofDist);       // mm

    Serial.print(",LDR:");
    Serial.print(ldrValue);

    Serial.print(",F:");
    Serial.print(fallDetected ? 1 : 0);

    Serial.println();

    lastPrint = now;
  }
}
