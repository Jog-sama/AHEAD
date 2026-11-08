// TactileVector's thumb lever alone, as a BLE peripheral named `Thumb`; the servo and its service are Thumb.h's, which
// the cane firmware also carries when one board serves both.
#include <Arduino.h>
#include <NimBLEDevice.h>
#include <esp_task_wdt.h>
#include "Thumb.h"

namespace {

volatile bool connected = false;

struct Server : NimBLEServerCallbacks {
  void onConnect(NimBLEServer*, NimBLEConnInfo& info) override {
    connected = true;
    thumb::onConnect();
    Serial.printf("ble: connected %s\n", info.getAddress().toString().c_str());
  }
  void onDisconnect(NimBLEServer*, NimBLEConnInfo&, int reason) override {
    connected = false;
    thumb::onDisconnect();
    Serial.printf("ble: disconnected (%d), neutral, advertising\n", reason);
    NimBLEDevice::startAdvertising();
  }
} server_callbacks;

void startBle() {
  NimBLEDevice::init("Thumb");
  NimBLEServer* server = NimBLEDevice::createServer();
  server->setCallbacks(&server_callbacks);
  thumb::addService(server);
  NimBLEAdvertising* adv = NimBLEDevice::getAdvertising();
  adv->setName("Thumb");
  adv->addServiceUUID(thumb::kServiceUuid);
  adv->start();
}

}  // namespace

void setup() {
  Serial.begin(115200);
#if ARDUINO_USB_CDC_ON_BOOT
  Serial.setTxTimeoutMs(0);  // a closed host port must never stall loop()
#endif
  thumb::setup();

  esp_task_wdt_config_t wdt = {.timeout_ms = 3000, .idle_core_mask = 0, .trigger_panic = true};
  if (esp_task_wdt_init(&wdt) == ESP_ERR_INVALID_STATE) esp_task_wdt_reconfigure(&wdt);
  esp_task_wdt_add(nullptr);

  startBle();
  Serial.println("thumb: advertising");
}

void loop() {
  static unsigned long log_at = 0;
  esp_task_wdt_reset();
  unsigned long now = millis();
  thumb::loop(now);
  if (now - log_at >= 1000) {
    log_at = now;
    thumb::print();
    Serial.printf(" ble=%s up=%lus\n", connected ? "connected" : "advertising", now / 1000);
  }
  delay(5);
}
