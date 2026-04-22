/*
 * ============================================================================
 *  SMART CANE CLIP-ON  |  MODULE A: ESP32 FIRMWARE ("Reflexes")
 * ============================================================================
 *  Tech      : C++ / Arduino (ESP32)
 *  Sensors   : 2x VL53L0X (ToF), MPU9052 (IMU), LDR (analog)
 *  Outputs   : 2x Vibration Motors, I2C OLED (SSD1306)
 *
 *  DATA PROTOCOL (NON-NEGOTIABLE):
 *      "dist_fwd,dist_drop,fall_flag,light_val"
 *      Example: "045,180,0,550"
 *
 *  WIRING QUICK REF (change if your PCB differs)
 *  ---------------------------------------------
 *    I2C SDA          -> GPIO 21
 *    I2C SCL          -> GPIO 22
 *    VL53 FWD XSHUT   -> GPIO 16   (disabled during init of DROP sensor)
 *    VL53 DROP XSHUT  -> GPIO 17
 *    Motor LEFT       -> GPIO 25   (PWM)
 *    Motor RIGHT      -> GPIO 26   (PWM)
 *    LDR (analog)     -> GPIO 34
 *
 *  LIBRARIES NEEDED (Arduino Library Manager):
 *    - Adafruit_VL53L0X
 *    - Adafruit_MPU6050  (works for MPU9052, drop-in)
 *    - Adafruit_SSD1306
 *    - Adafruit_GFX
 * ============================================================================
 */

#include <Wire.h>
#include <Adafruit_VL53L0X.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_SSD1306.h>

// ---------- PIN MAP ----------
#define XSHUT_FWD   16
#define XSHUT_DROP  17
#define MOTOR_L     25
#define MOTOR_R     26
#define LDR_PIN     34

// ---------- I2C ADDRESSES ----------
#define ADDR_VL53_FWD   0x30
#define ADDR_VL53_DROP  0x31

// ---------- TUNING ----------
#define LOOP_MS          100     // 10 Hz packet rate
#define FALL_ACCEL_G     2.5f    // > this = possible fall
#define MOTION_DELTA_MM  30      // change required to count as "approaching"
#define OBSTACLE_FWD_MM  500     // buzz when closer than this
#define DROP_DIFF_MM     150     // buzz when drop exceeds this

// ---------- GLOBAL OBJECTS ----------
Adafruit_VL53L0X loxFwd  = Adafruit_VL53L0X();
Adafruit_VL53L0X loxDrop = Adafruit_VL53L0X();
Adafruit_MPU6050 mpu;
Adafruit_SSD1306 oled(128, 64, &Wire, -1);

// ---------- STATE ----------
uint16_t prevFwd  = 0;
uint16_t prevDrop = 0;
unsigned long lastTick = 0;

// ===========================================================================
//  HELPERS
// ===========================================================================
void buzz(uint8_t pin, uint8_t strength, uint16_t ms) {
  analogWrite(pin, strength);
  delay(ms);
  analogWrite(pin, 0);
}

bool initDualVL53() {
  // Dual VL53L0X trick: hold both in reset, bring up one at a time,
  // assign a unique I2C address, then bring up the next.
  pinMode(XSHUT_FWD,  OUTPUT);
  pinMode(XSHUT_DROP, OUTPUT);
  digitalWrite(XSHUT_FWD,  LOW);
  digitalWrite(XSHUT_DROP, LOW);
  delay(10);

  // Bring up FWD
  digitalWrite(XSHUT_FWD, HIGH);
  delay(10);
  if (!loxFwd.begin(ADDR_VL53_FWD)) return false;

  // Bring up DROP
  digitalWrite(XSHUT_DROP, HIGH);
  delay(10);
  if (!loxDrop.begin(ADDR_VL53_DROP)) return false;

  return true;
}

// VIBECODER ZONE ------------------------------------------------------------
// Put your custom haptic pattern / alert logic here.
// Called every loop with the freshly-computed sensor values.
// ---------------------------------------------------------------------------
void reflexLogic(uint16_t distFwd, uint16_t distDrop, bool fall, int light) {
  // Obstacle getting closer?
  if (distFwd > 0 && distFwd < OBSTACLE_FWD_MM &&
      (prevFwd == 0 || (int)prevFwd - (int)distFwd > MOTION_DELTA_MM)) {
    buzz(MOTOR_L, 200, 40);
  }

  // Sudden drop-off (stairs / kerb)?
  if (distDrop > 0 && (int)distDrop - (int)prevDrop > DROP_DIFF_MM) {
    buzz(MOTOR_R, 255, 80);
  }

  // Fall detected -> both motors scream
  if (fall) {
    buzz(MOTOR_L, 255, 200);
    buzz(MOTOR_R, 255, 200);
  }

  // TODO (vibecoder): add light-based behavior using `light`
}

void drawOLED(uint16_t f, uint16_t d, bool fall, int light) {
  oled.clearDisplay();
  oled.setCursor(0, 0);
  oled.setTextSize(1);
  oled.setTextColor(SSD1306_WHITE);
  oled.printf("FWD : %4u mm\n", f);
  oled.printf("DROP: %4u mm\n", d);
  oled.printf("FALL: %s\n", fall ? "YES" : "no");
  oled.printf("LUX : %4d\n", light);
  oled.display();
}

// ===========================================================================
//  SETUP
// ===========================================================================
void setup() {
  Serial.begin(115200);
  delay(200);
  Wire.begin();

  pinMode(MOTOR_L, OUTPUT);
  pinMode(MOTOR_R, OUTPUT);

  if (!initDualVL53()) {
    Serial.println("ERR: VL53L0X init failed");
  }
  if (!mpu.begin()) {
    Serial.println("ERR: MPU init failed");
  }
  if (!oled.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println("ERR: OLED init failed");
  }

  oled.clearDisplay();
  oled.setCursor(0, 0);
  oled.setTextSize(1);
  oled.setTextColor(SSD1306_WHITE);
  oled.println("Smart Cane Ready");
  oled.display();
}

// ===========================================================================
//  MAIN LOOP - emits packet every LOOP_MS
// ===========================================================================
void loop() {
  if (millis() - lastTick < LOOP_MS) return;
  lastTick = millis();

  // ---- Read ToF sensors ----
  VL53L0X_RangingMeasurementData_t mFwd, mDrop;
  loxFwd.rangingTest(&mFwd, false);
  loxDrop.rangingTest(&mDrop, false);
  uint16_t distFwd  = (mFwd.RangeStatus  != 4) ? mFwd.RangeMilliMeter  : 0;
  uint16_t distDrop = (mDrop.RangeStatus != 4) ? mDrop.RangeMilliMeter : 0;

  // ---- Read IMU & compute fall ----
  sensors_event_t a, g, t;
  mpu.getEvent(&a, &g, &t);
  float accMag = sqrt(a.acceleration.x * a.acceleration.x +
                      a.acceleration.y * a.acceleration.y +
                      a.acceleration.z * a.acceleration.z) / 9.81f;
  bool fallFlag = (accMag > FALL_ACCEL_G);

  // ---- Read LDR ----
  int lightVal = analogRead(LDR_PIN);   // 0..4095 on ESP32

  // ---- React ----
  reflexLogic(distFwd, distDrop, fallFlag, lightVal);
  drawOLED(distFwd, distDrop, fallFlag, lightVal);

  // ---- Emit packet: "045,180,0,550" ----
  char buf[32];
  snprintf(buf, sizeof(buf), "%03u,%03u,%d,%04d",
           distFwd, distDrop, fallFlag ? 1 : 0, lightVal);
  Serial.println(buf);

  // ---- Save deltas ----
  prevFwd  = distFwd;
  prevDrop = distDrop;
}
