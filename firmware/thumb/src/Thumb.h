#pragma once
// The thumb lever's servo and its GATT service, for any NimBLE server: firmware/thumb runs it alone as `Thumb`, and the
// cane firmware adds it beside its own service when built with CANE_THUMB. The contract is in README.md and shared with
// ios/Ahead/index.html. Limits, PWM math and the 800 ms timeout are firmware/TactileVector/Safety.h's.
#include <Arduino.h>
#include <NimBLEDevice.h>
#include "driver/gpio.h"
#include "Safety.h"

#if __has_include("config.h")
#include "config.h"
#else
#include "config.example.h"
#endif

namespace thumb {
namespace {

const char kServiceUuid[] = "c0de0011-ca9e-4a11-8e8d-000000000001";
const char kAngleUuid[] = "c0de0012-ca9e-4a11-8e8d-000000000001";
const char kStatusUuid[] = "c0de0013-ca9e-4a11-8e8d-000000000001";

constexpr uint8_t kFlagDisabled = 1, kFlagNeutralHold = 2;
constexpr unsigned long kStatusEveryMs = 1000;

SemaphoreHandle_t servo_mutex;
bool configured = false;  // PWM attached and the last write succeeded
bool failsafe = true;     // neutral because no fresh command holds another angle
int current = safety::NEUTRAL;
uint32_t last_command = 0;
volatile bool connected = false;
NimBLECharacteristic* status_chr;
uint8_t status[2] = {0, 0};

// Strapping, flash, USB and UART pins carry no servo.
bool pinUsable(int pin) {
  if (pin < 0 || !GPIO_IS_VALID_OUTPUT_GPIO(pin)) return false;
#if CONFIG_IDF_TARGET_ESP32C3
  return pin != 2 && pin != 8 && pin != 9 && !(pin >= 11 && pin <= 21);
#else
  return pin != 0 && pin != 1 && pin != 2 && pin != 3 && pin != 5 && !(pin >= 6 && pin <= 12) && pin != 15;
#endif
}

// Called with servo_mutex held. A failed write stops the pulses altogether, so LEDC cannot keep driving the last angle.
bool writeLocked(int angle) {
  if (!configured) return false;
  if (!ledcWrite(SERVO_PIN, safety::duty(angle))) {
    configured = false;
    ledcDetach(SERVO_PIN);
    pinMode(SERVO_PIN, OUTPUT);
    digitalWrite(SERVO_PIN, LOW);
    return false;
  }
  current = angle;
  return true;
}

void neutralLocked() {
  if (!failsafe) {
    writeLocked(safety::NEUTRAL);
    failsafe = true;
  }
}

// Its own task, so the timeout holds even if the BLE host or loop() stalls.
void watchdogTask(void*) {
  for (;;) {
    xSemaphoreTake(servo_mutex, portMAX_DELAY);
    if (!connected || safety::expired(millis(), last_command)) neutralLocked();
    xSemaphoreGive(servo_mutex);
    vTaskDelay(pdMS_TO_TICKS(10));
  }
}

// One byte, the angle in degrees; anything outside 60..120 is dropped and the timeout keeps running.
struct AngleWrite : NimBLECharacteristicCallbacks {
  void onWrite(NimBLECharacteristic* chr, NimBLEConnInfo&) override {
    NimBLEAttValue v = chr->getValue();
    if (v.size() != 1) return;
    int angle = v.data()[0];
    if (angle < safety::MIN_ANGLE || angle > safety::MAX_ANGLE) return;
    xSemaphoreTake(servo_mutex, portMAX_DELAY);
    if (writeLocked(angle)) {
      last_command = millis();
      failsafe = false;
    }
    xSemaphoreGive(servo_mutex);
  }
} angle_write;

}  // namespace

// Before the BLE server exists: PWM at neutral, or none until config.h names a verified pin and supply.
void setup() {
  servo_mutex = xSemaphoreCreateMutex();
  if (PIN_VERIFIED && POWER_VERIFIED && pinUsable(SERVO_PIN) && ledcAttach(SERVO_PIN, 50, 14)) {
    configured = true;
    failsafe = false;
    neutralLocked();
  }
  Serial.println(configured ? "thumb: PWM ready, neutral. Keep the horn unloaded until calibrated."
                            : "thumb: SAFE DISABLED, no PWM: set SERVO_PIN, PIN_VERIFIED, POWER_VERIFIED in config.h");
  if (xTaskCreate(watchdogTask, "servoFailsafe", 3072, nullptr, 3, nullptr) != pdPASS) {
    if (configured) ledcDetach(SERVO_PIN);
    configured = false;
    Serial.println("thumb: FATAL, watchdog task unavailable; PWM detached");
  }
}

void addService(NimBLEServer* server) {
  NimBLEService* svc = server->createService(kServiceUuid);
  NimBLECharacteristic* angle = svc->createCharacteristic(kAngleUuid, NIMBLE_PROPERTY::WRITE_NR);
  angle->createDescriptor("2901", NIMBLE_PROPERTY::READ, 24)->setValue("angle");
  angle->setCallbacks(&angle_write);
  status_chr = svc->createCharacteristic(kStatusUuid, NIMBLE_PROPERTY::NOTIFY);
  status_chr->createDescriptor("2901", NIMBLE_PROPERTY::READ, 24)->setValue("status");
}

void onConnect() { connected = true; }

void onDisconnect() {
  connected = false;
  xSemaphoreTake(servo_mutex, portMAX_DELAY);
  neutralLocked();
  xSemaphoreGive(servo_mutex);
}

// From loop(): the angle as the board holds it, so the page can tell a write that arrived from one that did not (the
// angle characteristic is write-without-response).
void loop(unsigned long now) {
  static uint8_t sent[2] = {0, 0xFF};
  static unsigned long status_at = 0;
  xSemaphoreTake(servo_mutex, portMAX_DELAY);
  status[0] = current;
  status[1] = (configured ? 0 : kFlagDisabled) | (failsafe ? kFlagNeutralHold : 0);
  xSemaphoreGive(servo_mutex);
  if (memcmp(status, sent, 2) || now - status_at >= kStatusEveryMs) {
    memcpy(sent, status, 2);
    status_at = now;
    status_chr->setValue(status, 2);
    if (connected) status_chr->notify();
  }
}

// For the serial line: angle=90 servo=ready neutral-hold
void print() {
  Serial.printf("angle=%u servo=%s %s", status[0], status[1] & kFlagDisabled ? "disabled" : "ready",
                status[1] & kFlagNeutralHold ? "neutral-hold" : "commanded");
}

}  // namespace thumb
