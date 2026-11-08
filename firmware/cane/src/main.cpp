// The GATT contract is in README.md and shared with ios/Ahead/index.html; a change here alone breaks the page. The phone's
// written state expires 1.5 s after the write so a dropped link neither silences the motor nor leaves it on.
#include <Arduino.h>
#include <NimBLEDevice.h>
#include <esp_task_wdt.h>
#ifdef CANE_SENSOR_VL53L0X
#include <VL53L0X.h>
#include <Wire.h>
#endif
#ifdef CANE_THUMB
#include "Thumb.h"  // the thumb lever's servo and service on this same board, from firmware/thumb
#endif

// Free on a C3 SuperMini: 8 is the LED, 9 the boot button, 18 and 19 the USB port, and 2 is a strapping pin that must
// read high at reset, so no button goes there. platformio.ini's devkit section remaps every pin for a classic ESP32.
#ifndef CANE_BUTTON_PIN
#define CANE_BUTTON_PIN 21  // to GND
#endif
#ifndef CANE_BOOT_PIN
#define CANE_BOOT_PIN 9  // the board's own button counts as the cane's, for the bench
#endif
#ifndef CANE_TRIG_PIN
#define CANE_TRIG_PIN 5
#endif
#ifndef CANE_ECHO_PIN
#define CANE_ECHO_PIN 6
#endif
#ifndef CANE_SDA_PIN
#define CANE_SDA_PIN 4
#endif
#ifndef CANE_SCL_PIN
#define CANE_SCL_PIN 3
#endif
#ifndef CANE_MOTOR_PIN
#define CANE_MOTOR_PIN 7  // the NPN's base through 1 k, with 10 k to GND so a reset's floating pin keeps the motor off
#endif
#ifndef CANE_BATTERY_PIN
#define CANE_BATTERY_PIN -1  // ADC1 is GPIO 0 to 4
#endif
#ifndef CANE_BATTERY_DIVIDER
#define CANE_BATTERY_DIVIDER 2  // (R_top + R_bottom) / R_bottom
#endif
#ifndef CANE_LED_PIN
#define CANE_LED_PIN 8
#endif
#ifndef CANE_LED_ON
#define CANE_LED_ON LOW
#endif

namespace {

const char kServiceUuid[] = "c0de0001-ca9e-4a11-8e8d-000000000001";
const char kDistanceUuid[] = "c0de0002-ca9e-4a11-8e8d-000000000001";
const char kButtonUuid[] = "c0de0003-ca9e-4a11-8e8d-000000000001";
const char kMotorUuid[] = "c0de0004-ca9e-4a11-8e8d-000000000001";
const char kStatusUuid[] = "c0de0005-ca9e-4a11-8e8d-000000000001";

constexpr uint16_t kNoReading = 0xFFFF;
constexpr uint16_t kFastUnderMm = 1000;
constexpr uint16_t kSettleBandMm = 100;
constexpr int kDeescalateFrames = 4;
constexpr unsigned long kFrameMs = 100;
constexpr unsigned long kPhoneHoldMs = 1500;
constexpr unsigned long kSettleMs = 5000;
constexpr unsigned long kLongPressMs = 600;
constexpr unsigned long kStatusEveryMs = 5000;
constexpr unsigned long kSensorStaleMs = 1000;
constexpr unsigned long kPulseMs = 100;
constexpr unsigned long kArmedMs = 300;  // one buzz, three pulses long, when the first phone connects
constexpr unsigned long kPeriodMs = 200;
constexpr uint8_t kBatteryUnknown = 0xFF;
constexpr uint8_t kFlagFault = 1, kFlagPhone = 2, kFlagSettled = 4;

// Written by the sensor task, read by loop().
volatile uint16_t reading = kNoReading;
volatile uint32_t frame = 0;
volatile unsigned long read_at = 0;
volatile bool sensor_fault = true;  // until the sensor answers, so the motor stays off at boot

// Written by the BLE host task, read by loop().
volatile uint8_t phone_state = 0;
volatile unsigned long phone_at = 0;
volatile bool phone_written = false;
volatile bool connected = false;
volatile bool paired = false;  // a phone has connected since boot; never cleared

NimBLECharacteristic* distance_chr;
NimBLECharacteristic* button_chr;
NimBLECharacteristic* status_chr;

uint8_t local_state = 0, played = 0;
int lower_frames = 0;
unsigned long phase_at = 0;
uint8_t battery = kBatteryUnknown;
uint16_t mm_min = kNoReading, mm_max = 0;

#ifdef CANE_SENSOR_VL53L0X

VL53L0X sensor;
bool found = false;

bool start() {
  Wire.end();
  Wire.begin(CANE_SDA_PIN, CANE_SCL_PIN);
  sensor.setTimeout(200);
  if (!sensor.init()) return false;
  // Long-range settings: about 2 m instead of 1.2 m, less precise up close.
  sensor.setSignalRateLimit(0.1);
  sensor.setVcselPulsePeriod(VL53L0X::VcselPeriodPreRange, 18);
  sensor.setVcselPulsePeriod(VL53L0X::VcselPeriodFinalRange, 14);
  sensor.setMeasurementTimingBudget(33000);
  sensor.startContinuous(kFrameMs);
  return true;
}

bool readOnce(uint16_t* mm) {
  if (!found) {
    found = start();
    if (!found) {
      vTaskDelay(pdMS_TO_TICKS(1000));
      return false;
    }
    Serial.printf("sensor: VL53L0X on SDA %d, SCL %d\n", CANE_SDA_PIN, CANE_SCL_PIN);
  }
  uint16_t r = sensor.readRangeContinuousMillimeters();
  if (sensor.timeoutOccurred()) {
    found = false;
    Serial.println("sensor: VL53L0X stopped answering");
    return false;
  }
  *mm = r >= 8000 ? kNoReading : r;  // 8190 and up: nothing in reach
  return true;
}

#else

volatile uint32_t echo_rise = 0, echo_fall = 0;
volatile uint8_t echo_edges = 0;

void IRAM_ATTR onEcho() {
  uint32_t now = micros();
  if (digitalRead(CANE_ECHO_PIN)) {
    echo_rise = now;
    echo_edges = 1;
  } else if (echo_edges == 1) {
    echo_fall = now;
    echo_edges = 2;
  }
}

// False with no echo edge at all (unpowered or unwired); kNoReading when the echo ran past 30 ms, which is how the
// sensor says nothing in reach (a JSN-SR04T holds ECHO up to about 60 ms then, so a hold still up at the next trigger
// is waited out first). A JSN-SR04T wants 60 ms between triggers and misses echoes on the HC-SR04's 10 us trigger;
// 20 us is reported reliable (forum.mysensors.org/topic/11417, NewPing issue 41).
bool readOnce(uint16_t* mm) {
  for (int i = 0; i < 50 && digitalRead(CANE_ECHO_PIN); i++) vTaskDelay(1);
  echo_edges = 0;
  digitalWrite(CANE_TRIG_PIN, HIGH);
  delayMicroseconds(20);
  digitalWrite(CANE_TRIG_PIN, LOW);
  vTaskDelay(pdMS_TO_TICKS(60));
  if (echo_edges == 0) return false;
  uint32_t us = echo_edges == 2 ? echo_fall - echo_rise : 60000;
  *mm = us > 30000 ? kNoReading : us * 343 / 2000;  // 343 m/s, there and back
  return true;
}

#endif

void sensorTask(void*) {
  int misses = 0;
  TickType_t last = xTaskGetTickCount();
  for (;;) {
    uint16_t mm = kNoReading;
    if (readOnce(&mm)) {
      misses = 0;
      read_at = millis();
      sensor_fault = false;
    } else if (++misses >= 10) {
      if (!sensor_fault) Serial.println("sensor: fault");
      sensor_fault = true;
    }
    reading = mm;
    frame = frame + 1;
    vTaskDelayUntil(&last, pdMS_TO_TICKS(kFrameMs));
  }
}

struct MotorWrite : NimBLECharacteristicCallbacks {
  void onWrite(NimBLECharacteristic* chr, NimBLEConnInfo&) override {
    NimBLEAttValue v = chr->getValue();
    if (v.size() < 1 || v.data()[0] > 2) return;
    phone_state = v.data()[0];
    phone_at = millis();
    phone_written = true;
  }
} motor_write;

struct Server : NimBLEServerCallbacks {
  void onConnect(NimBLEServer*, NimBLEConnInfo& info) override {
    connected = true;
    paired = true;
#ifdef CANE_THUMB
    thumb::onConnect();
#endif
    Serial.printf("ble: connected %s\n", info.getAddress().toString().c_str());
  }
  void onDisconnect(NimBLEServer*, NimBLEConnInfo&, int reason) override {
    connected = false;
#ifdef CANE_THUMB
    thumb::onDisconnect();
#endif
    Serial.printf("ble: disconnected (%d), advertising\n", reason);
    NimBLEDevice::startAdvertising();
  }
} server_callbacks;

NimBLECharacteristic* characteristic(NimBLEService* svc, const char* uuid, uint32_t props, const char* name) {
  NimBLECharacteristic* chr = svc->createCharacteristic(uuid, props);
  chr->createDescriptor("2901", NIMBLE_PROPERTY::READ, 24)->setValue(name);
  return chr;
}

// "Cane 3F2A" (firmware/thumb names its board the same way): the base and the last two bytes of the board's Bluetooth address, so two boards in range read apart in
// the app and on a label. After NimBLEDevice::init.
std::string boardName(const char* base) {
  std::string a = NimBLEDevice::getAddress().toString();  // aa:bb:cc:dd:ee:ff
  std::string id = a.substr(12, 2) + a.substr(15, 2);
  for (char& c : id) c = toupper(c);
  return std::string(base) + " " + id;
}

std::string name;

// The name goes in the scan response with the lever's service, since flags, the cane's 128-bit UUID and an 11-byte name
// overflow one 31-byte packet.
void startBle() {
  NimBLEDevice::init("Cane");
  name = boardName("Cane");
  NimBLEDevice::setDeviceName(name);
  NimBLEServer* server = NimBLEDevice::createServer();
  server->setCallbacks(&server_callbacks);
  NimBLEService* svc = server->createService(kServiceUuid);
  distance_chr = characteristic(svc, kDistanceUuid, NIMBLE_PROPERTY::NOTIFY, "distance mm");
  button_chr = characteristic(svc, kButtonUuid, NIMBLE_PROPERTY::NOTIFY, "button");
  NimBLECharacteristic* motor = characteristic(svc, kMotorUuid, NIMBLE_PROPERTY::WRITE_NR, "motor");
  motor->setCallbacks(&motor_write);
  status_chr = characteristic(svc, kStatusUuid, NIMBLE_PROPERTY::NOTIFY, "status");
  NimBLEAdvertising* adv = NimBLEDevice::getAdvertising();
  adv->addServiceUUID(kServiceUuid);
  NimBLEAdvertisementData scan;
  scan.setName(name);
#ifdef CANE_THUMB
  thumb::addService(server);
  scan.addServiceUUID(thumb::kServiceUuid);
#endif
  adv->setScanResponseData(scan);
  adv->enableScanResponse(true);
  adv->start();
}

void notify(NimBLECharacteristic* chr, const uint8_t* value, size_t len) {
  chr->setValue(value, len);
  if (connected) chr->notify();
}

void readBattery() {
#if CANE_BATTERY_PIN >= 0
  static uint32_t sum = 0;
  static int n = 0;
  sum += analogReadMilliVolts(CANE_BATTERY_PIN) * CANE_BATTERY_DIVIDER;
  if (++n < 8) return;
  int mv = sum / n;
  sum = 0, n = 0;
  int pct = constrain((mv - 3300) * 100 / (4200 - 3300), 0, 100);  // a 1S lithium cell, linear between empty and full
  if (battery == kBatteryUnknown || abs(pct - battery) >= 2) battery = pct;  // ADC noise would otherwise notify status every second
#endif
}

// Debounced by a 20 ms tick, as the gateway's: down after two ticks.
void pollButton(unsigned long now) {
  static unsigned long tick_at = 0, down_at = 0;
  static int down_ticks = 0;
  static bool down = false, long_sent = false;
  if (now - tick_at < 20) return;
  tick_at = now;
  bool pressed = digitalRead(CANE_BUTTON_PIN) == LOW || digitalRead(CANE_BOOT_PIN) == LOW;
  down_ticks = pressed ? min(down_ticks + 1, 3) : 0;
  bool now_down = down_ticks >= 2;
  if (now_down && !down) down_at = now, long_sent = false;
  if (now_down && !long_sent && now - down_at >= kLongPressMs) {
    uint8_t v = 2;
    notify(button_chr, &v, 1);
    Serial.println("button: long");
    long_sent = true;
  }
  if (!now_down && down && !long_sent) {
    uint8_t v = 1;
    notify(button_chr, &v, 1);
    Serial.println("button: short");
  }
  down = now_down;
}

}  // namespace

void setup() {
  pinMode(CANE_MOTOR_PIN, OUTPUT);
  digitalWrite(CANE_MOTOR_PIN, LOW);
  pinMode(CANE_LED_PIN, OUTPUT);
  digitalWrite(CANE_LED_PIN, !CANE_LED_ON);
  pinMode(CANE_BUTTON_PIN, INPUT_PULLUP);
  pinMode(CANE_BOOT_PIN, INPUT_PULLUP);
#ifdef CANE_GND_PIN
  pinMode(CANE_GND_PIN, OUTPUT);  // a ground for the button on a board short of GND pins
  digitalWrite(CANE_GND_PIN, LOW);
#endif
#ifndef CANE_SENSOR_VL53L0X
  pinMode(CANE_TRIG_PIN, OUTPUT);
  digitalWrite(CANE_TRIG_PIN, LOW);
  pinMode(CANE_ECHO_PIN, INPUT);
  attachInterrupt(digitalPinToInterrupt(CANE_ECHO_PIN), onEcho, CHANGE);
#endif
#if CANE_BATTERY_PIN >= 0
  analogSetPinAttenuation(CANE_BATTERY_PIN, ADC_11db);
#endif
  Serial.begin(115200);
#if ARDUINO_USB_CDC_ON_BOOT
  Serial.setTxTimeoutMs(0);  // a closed host port must never stall loop(): the watchdog tripped three times on it
#endif

  // The Arduino core starts the task watchdog without loop() in it; 3 s, a panic and a reset if loop() stalls.
  esp_task_wdt_config_t wdt = {.timeout_ms = 3000, .idle_core_mask = 0, .trigger_panic = true};
  if (esp_task_wdt_init(&wdt) == ESP_ERR_INVALID_STATE) esp_task_wdt_reconfigure(&wdt);
  esp_task_wdt_add(nullptr);

#ifdef CANE_THUMB
  thumb::setup();
#endif
  xTaskCreate(sensorTask, "sensor", 4096, nullptr, 2, nullptr);
  startBle();
  Serial.printf("cane: %s, advertising as %s\n", esp_reset_reason() == ESP_RST_BROWNOUT ? "after a brown-out" : "up",
                name.c_str());
}

void loop() {
  static uint32_t seen_frame = 0;
  static unsigned long status_at = 0, log_at = 0, battery_at = 0;
  static uint8_t sent_status[3] = {0, 0, 0};
  static uint16_t settle_mm = kNoReading;
  static unsigned long settle_at = 0;
  static unsigned long armed_at = 0;
  esp_task_wdt_reset();
  unsigned long now = millis();

  if (frame != seen_frame) {
    seen_frame = frame;
    uint16_t mm = reading;
    notify(distance_chr, (uint8_t*)&mm, 2);
    if (mm != kNoReading) mm_min = min(mm_min, mm), mm_max = max(mm_max, mm);
    if (mm == kNoReading || abs((int)mm - (int)settle_mm) > kSettleBandMm) settle_mm = mm, settle_at = now;
    uint8_t want = mm < kFastUnderMm ? 2 : 0;
    if (want >= local_state) {
      local_state = want;
      lower_frames = 0;
    } else if (++lower_frames >= kDeescalateFrames) {
      local_state = want;
      lower_frames = 0;
    }
  }

  bool fault = sensor_fault || now - read_at > kSensorStaleMs;
  bool phone_live = phone_written && now - phone_at < kPhoneHoldMs;
  uint8_t phone = phone_live ? phone_state : 0;
  // A reading steady for 5 s is a thing the hand has already felt: the cane's own cue rests until it moves by 10 cm,
  // as the BuzzClip sleeps after 5–7 s at a fixed distance (its manual: irritation while standing near something).
  bool settled = local_state && settle_mm != kNoReading && now - settle_at >= kSettleMs;
  uint8_t own = settled ? 0 : local_state;
  // A faulty sensor must not drive the motor, but the phone still may: its cue is independent of this sensor.
  uint8_t next = fault ? phone : max(own, phone);
  // The grip buzzes only under 1 m: steady pulses there mask the ground texture the cane carries, and the chest
  // already pulses from 2.5 m. A phone's 1 (slow) is held and echoed but plays nothing. Silent until a phone has
  // connected once, so a board on the bench or just powered on is quiet; a drop mid-walk keeps the cane warning.
  if (next < 2 || !paired) next = 0;
  if (next != played) {
    played = next;
    phase_at = now;  // a change starts with a pulse
  }
  // Silence before this buzz means the cane is not warning yet; the LED says the same only to someone who can see it.
  if (paired && !armed_at) armed_at = now | 1;
  bool armed_buzz = armed_at && now - armed_at < kArmedMs;
  digitalWrite(CANE_MOTOR_PIN, armed_buzz || (played && (now - phase_at) % kPeriodMs < kPulseMs));
  digitalWrite(CANE_LED_PIN, connected ? CANE_LED_ON : !CANE_LED_ON);

  pollButton(now);
#ifdef CANE_THUMB
  thumb::loop(now);
#endif

  if (now - battery_at >= 125) {
    battery_at = now;
    readBattery();
  }
  bool phone_plays = !fault && played && phone >= own;
  // The third byte is the phone's motor value as the cane holds it, so the page can tell a write that arrived from one
  // that did not (the characteristic is write-without-response).
  uint8_t status[3] = {battery, (uint8_t)((fault ? kFlagFault : 0) | (phone_plays ? kFlagPhone : 0) |
                                          (settled ? kFlagSettled : 0)), phone};
  if (memcmp(status, sent_status, 3) || now - status_at >= kStatusEveryMs) {
    memcpy(sent_status, status, 3);
    status_at = now;
    notify(status_chr, status, 3);
  }

  if (now - log_at >= 1000) {
    log_at = now;
    uint16_t mm = reading;
    if (mm == kNoReading) Serial.print("mm=none");
    else Serial.printf("mm=%u", mm);
    if (mm_min != kNoReading) Serial.printf(" (%u-%u)", mm_min, mm_max);
    Serial.printf(" local=%u%s phone=%u played=%u fault=%d bat=%u ble=%s up=%lus reset=%d\n", local_state,
                  settled ? " settled" : "", phone, played, fault, battery, connected ? "connected" : "advertising",
                  now / 1000, (int)esp_reset_reason());
#ifdef CANE_THUMB
    Serial.print("  thumb: ");
    thumb::print();
    Serial.println();
#endif
    mm_min = kNoReading, mm_max = 0;
  }
  delay(5);
}
