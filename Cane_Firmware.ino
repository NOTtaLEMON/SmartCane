/*
 * ============================================================================
 *  SMART CANE CLIP-ON  |  ESP32 FIRMWARE
 * ============================================================================
 *  Hardware (actual):
 *    - 1x VL53L0X ToF (forward distance)
 *    - 16x2 LCD via I2C (LiquidCrystal_I2C @ 0x27)
 *    - LED         -> GPIO 2
 *    - Buzzer      -> GPIO 4
 *    - LDR (analog)-> GPIO 34
 *    - I2C SDA     -> GPIO 21
 *    - I2C SCL     -> GPIO 22
 *
 *  DATA PROTOCOL (NON-NEGOTIABLE -- matches dashboard parser):
 *      "dist_fwd,dist_drop,fall_flag,light_val"
 *      e.g. "045,000,0,0550"
 *      dist_drop = 000  (no drop sensor on this build)
 *      fall_flag = 0    (no IMU on this build)
 *
 *  LIBRARIES NEEDED (Arduino Library Manager):
 *    - Adafruit VL53L0X
 *    - LiquidCrystal I2C  (by Frank de Brabander)
 * ============================================================================
 */

#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <Adafruit_VL53L0X.h>

// ---------- PIN MAP ----------
#define LED_PIN     2
#define BUZZER_PIN  4
#define LDR_PIN     34

// ---------- TUNING ----------
#define LDR_DARK_THRESHOLD  700   // below this = dark -> LED on
#define LOOP_MS             100   // 10 Hz packet rate

// ---------- OBJECTS ----------
LiquidCrystal_I2C lcd(0x27, 16, 2);
Adafruit_VL53L0X lox = Adafruit_VL53L0X();

unsigned long lastTick = 0;

// ===========================================================================
//  SETUP
// ===========================================================================
void setup() {
  Serial.begin(115200);
  delay(1000);

  Wire.begin(21, 22);

  pinMode(LED_PIN,    OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);

  lcd.init();
  lcd.backlight();
  lcd.setCursor(0, 0);
  lcd.print("Starting...");

  if (!lox.begin()) {
    lcd.clear();
    lcd.print("TOF FAIL");
    Serial.println("ERR: VL53L0X init failed");
    while (1);
  }

  lcd.clear();
  lcd.print("READY");
  delay(1000);
}

// ===========================================================================
//  MAIN LOOP
// ===========================================================================
void loop() {
  if (millis() - lastTick < LOOP_MS) return;
  lastTick = millis();

  // ---- ToF ----
  VL53L0X_RangingMeasurementData_t measure;
  lox.rangingTest(&measure, false);
  int distFwd = (measure.RangeStatus != 4) ? (int)measure.RangeMilliMeter : 0;

  // ---- LDR ----
  int ldrValue = analogRead(LDR_PIN);
  bool isDark  = (ldrValue < LDR_DARK_THRESHOLD);

  // ---- LED ----
  digitalWrite(LED_PIN, isDark ? HIGH : LOW);

  // ---- Buzzer ----
  if (distFwd > 0 && distFwd < 100) {
    // Very close -- fast beep
    digitalWrite(BUZZER_PIN, HIGH);
    delay(100);
    digitalWrite(BUZZER_PIN, LOW);
  } else if (distFwd > 0 && distFwd < 300) {
    // Approaching -- slow beep
    digitalWrite(BUZZER_PIN, HIGH);
    delay(300);
    digitalWrite(BUZZER_PIN, LOW);
  } else {
    digitalWrite(BUZZER_PIN, LOW);
  }

  // ---- LCD ----
  lcd.clear();
  lcd.setCursor(0, 0);
  if (measure.RangeStatus != 4) {
    lcd.print("Dist:");
    lcd.print(distFwd);
    lcd.print("mm");
  } else {
    lcd.print("Out of range");
  }
  lcd.setCursor(0, 1);
  lcd.print("L:");
  lcd.print(ldrValue);
  lcd.print(" ");
  lcd.print(isDark ? "DARK" : "BRIGHT");

  // ---- Serial packet (dashboard format) ----
  // Format: dist_fwd,dist_drop,fall_flag,light_val
  // dist_drop=000 (no drop sensor), fall_flag=0 (no IMU)
  char buf[32];
  snprintf(buf, sizeof(buf), "%03d,000,0,%04d", distFwd, ldrValue);
  Serial.println(buf);
}
