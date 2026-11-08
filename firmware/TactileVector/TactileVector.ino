
#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include <esp_arduino_version.h>
#include "driver/gpio.h"
#include "Safety.h"

#if __has_include("config.h")
#include "config.h"
#else
#include "config.example.h"
#endif

#if ESP_ARDUINO_VERSION_MAJOR != 3
#error "Use Arduino-ESP32 3.x (project tested target: 3.2.0)."
#endif

#if !defined(CONFIG_IDF_TARGET_ESP32C3)
#error "Select ESP32C3 Dev Module; this sketch targets ESP32-C3."
#endif

// ============================================================
// HARDWARE
// ============================================================

// SG90 servo on SERVO_PIN from config.h.
// External push button: GPIO3 -> button -> GND.
constexpr uint8_t BUTTON_PIN = 3;
constexpr uint32_t BUTTON_DEBOUNCE_MS = 40;

// ============================================================
// CONTROLLER STATE
// ============================================================

WebServer server(80);
SemaphoreHandle_t servoMutex;

bool configured = false;
bool pwmReady = false;
bool failsafeActive = true;

int currentAngle = safety::NEUTRAL;
uint32_t lastCommand = 0;
uint32_t buttonPressCount = 0;  // incremented on debounced press

// ============================================================
// AUTHENTICATION
// ============================================================

bool tokenValid() {
  const String provided = server.header("X-Device-Token");
  const char* expected = DEVICE_TOKEN;

  size_t n = strlen(expected);
  if (provided.length() != n) return false;

  unsigned char diff = 0;

  for (size_t i = 0; i < n; ++i) {
    diff |= provided[i] ^ expected[i];
  }

  return diff == 0;
}

// ============================================================
// SERVO CONTROL
// ============================================================

bool writeAngleLocked(int angle) {
  if (!pwmReady || !ledcWrite(SERVO_PIN, safety::duty(angle))) {
    return false;
  }

  currentAngle = angle;
  return true;
}

String statusJson() {
  xSemaphoreTake(servoMutex, portMAX_DELAY);

  String result =
    String("{\"ok\":") + (configured ? "true" : "false") +
    ",\"configured\":" + (configured ? "true" : "false") +
    ",\"angle\":" + String(currentAngle) +
    ",\"neutral\":90,\"min_angle\":60,\"max_angle\":120" +
    ",\"timeout_ms\":800,\"failsafe\":" +
    (failsafeActive ? "true" : "false") +
    ",\"wifi\":" +
    (WiFi.status() == WL_CONNECTED ? "true" : "false") +
    ",\"uptime_ms\":" + String(millis()) +
    ",\"pwm_hz\":50,\"pwm_bits\":14}";

  xSemaphoreGive(servoMutex);

  return result;
}

// ============================================================
// SAFETY WATCHDOG
// ============================================================

// Independent task: timeout still runs if synchronous
// HTTP client handling stalls.
void watchdogTask(void*) {
  for (;;) {
    xSemaphoreTake(servoMutex, portMAX_DELAY);

    if (
      configured &&
      (
        WiFi.status() != WL_CONNECTED ||
        safety::expired(millis(), lastCommand)
      )
    ) {
      if (!failsafeActive) {
        if (!writeAngleLocked(safety::NEUTRAL)) {
          configured = false;
        }

        failsafeActive = true;
      }
    }

    xSemaphoreGive(servoMutex);

    vTaskDelay(pdMS_TO_TICKS(10));
  }
}

// ============================================================
// PHYSICAL BUTTON
// ============================================================

void checkPushButton() {
  static int lastRawState = HIGH;
  static int stableState = HIGH;
  static uint32_t lastChangeMs = 0;

  int rawState = digitalRead(BUTTON_PIN);
  uint32_t now = millis();

  // Reset debounce timer whenever raw input changes.
  if (rawState != lastRawState) {
    lastChangeMs = now;
    lastRawState = rawState;
  }

  // Only accept the new state after it remains stable.
  if (
    rawState != stableState &&
    (uint32_t)(now - lastChangeMs) >= BUTTON_DEBOUNCE_MS
  ) {
    stableState = rawState;

    if (stableState == LOW) {
      buttonPressCount++;
      Serial.println("BUTTON PRESSED");
    } else {
      Serial.println("BUTTON RELEASED");
    }
  }
}

// ============================================================
// SETUP
// ============================================================

void setup() {
  Serial.begin(115200);

  // External push button on GPIO3.
  // Internal pull-up keeps input HIGH until button is pressed.
  pinMode(BUTTON_PIN, INPUT_PULLUP);

  Serial.println("TactileVector starting...");
  Serial.println("Push button configured on GPIO3.");

  servoMutex = xSemaphoreCreateMutex();

  if (!servoMutex) {
    Serial.println("FATAL: mutex allocation");
    return;
  }

  // Hardware and credential validation.
  bool pinOkay =
    SERVO_PIN >= 0 &&
    GPIO_IS_VALID_OUTPUT_GPIO(SERVO_PIN) &&
    SERVO_PIN != 2 &&
    SERVO_PIN != 8 &&
    SERVO_PIN != 9 &&
    SERVO_PIN != 18 &&
    SERVO_PIN != 19 &&
    !(SERVO_PIN >= 11 && SERVO_PIN <= 17) &&
    SERVO_PIN != 20 &&
    SERVO_PIN != 21;

  bool secretsOkay =
    strlen(DEVICE_TOKEN) >= 24 &&
    strncmp(DEVICE_TOKEN, "REPLACE", 7) != 0 &&
    strncmp(WIFI_SSID, "REPLACE", 7) != 0;

  if (
    PIN_VERIFIED &&
    POWER_VERIFIED &&
    pinOkay &&
    secretsOkay
  ) {
    pwmReady = ledcAttach(SERVO_PIN, 50, 14);

    configured =
      pwmReady &&
      writeAngleLocked(safety::NEUTRAL);
  }

  Serial.println(
    configured
      ? "PWM ready; neutral. Keep horn unloaded."
      : "SAFE DISABLED: verify config.h, GPIO, 5V power, and credentials. No servo PWM."
  );

  if (
    xTaskCreate(
      watchdogTask,
      "servoFailsafe",
      3072,
      nullptr,
      3,
      nullptr
    ) != pdPASS
  ) {
    if (pwmReady) {
      ledcDetach(SERVO_PIN);
    }

    configured = false;
    pwmReady = false;

    Serial.println(
      "FATAL: watchdog task unavailable; PWM detached"
    );
  }

  // ==========================================================
  // WIFI
  // ==========================================================

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  const char* headerKeys[] = {
    "X-Device-Token"
  };

  server.collectHeaders(headerKeys, 1);

  // ==========================================================
  // HEALTH ENDPOINT
  // ==========================================================

  server.on("/health", HTTP_GET, []() {
    server.sendHeader("Cache-Control", "no-store");

    server.send(
      200,
      "application/json",
      statusJson()
    );
  });

  // ==========================================================
  // SERVO STEERING ENDPOINT
  // ==========================================================

  // Read-only: no servo actuation and no Wi-Fi credentials exposed.
  server.on("/button", HTTP_GET, []() {
    server.sendHeader("Cache-Control", "no-store");
    if (!tokenValid()) {
      server.send(401, "application/json", "{\"error\":\"unauthorized\"}");
      return;
    }
    String body = String("{\"press_count\":") + String(buttonPressCount) +
      ",\"pressed\":" + (digitalRead(3) == LOW ? "true" : "false") + "}";
    server.send(200, "application/json", body);
  });
  server.on("/steer", HTTP_GET, []() {
    server.sendHeader("Cache-Control", "no-store");

    if (!tokenValid()) {
      server.send(
        401,
        "application/json",
        "{\"error\":\"unauthorized\"}"
      );
      return;
    }

    int angle = 90;

    if (
      server.args() != 1 ||
      !server.hasArg("angle") ||
      !safety::parseAngle(
        server.arg("angle").c_str(),
        angle
      )
    ) {
      server.send(
        400,
        "application/json",
        "{\"error\":\"exactly one integer angle 60..120 required\"}"
      );
      return;
    }

    xSemaphoreTake(servoMutex, portMAX_DELAY);

    bool ready =
      configured &&
      WiFi.status() == WL_CONNECTED;

    if (ready) {
      ready = writeAngleLocked(angle);

      if (ready) {
        lastCommand = millis();
        failsafeActive = false;
      } else {
        configured = false;
      }
    }

    xSemaphoreGive(servoMutex);

    server.send(
      ready ? 200 : 503,
      "application/json",
      statusJson()
    );
  });

  server.onNotFound([]() {
    server.send(
      404,
      "application/json",
      "{\"error\":\"not found\"}"
    );
  });

  server.begin();

  Serial.println("HTTP server started.");
  Serial.println("Press the GPIO3 button to test.");
}

// ============================================================
// MAIN LOOP
// ============================================================

void loop() {
  if (!servoMutex) {
    delay(100);
    return;
  }

  // Wi-Fi status reporting.
  static bool wasConnected = false;

  bool connected =
    WiFi.status() == WL_CONNECTED;

  if (connected && !wasConnected) {
    Serial.print("ESP32 address: http://");
    Serial.println(WiFi.localIP());
  }

  wasConnected = connected;

  // HTTP server.
  server.handleClient();

  // Read the physical push button.
  checkPushButton();

  delay(2);
}
