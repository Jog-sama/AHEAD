#!/usr/bin/env python3
"""Idempotently add authenticated button event counter to EXISTING sketch.

Preserves the existing SERVO_PIN, WiFi config, /steer, and independent watchdog.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import shutil
import time


def patch(text: str) -> str:
    if 'server.on("/button"' in text:
        return text
    needle = 'uint32_t lastCommand = 0;'
    if needle not in text:
        raise ValueError("Firmware layout differs; no changes applied")
    text = text.replace(needle, needle + '\nuint32_t buttonPressCount = 0;  // incremented on debounced press')

    if 'void checkPushButton()' in text:
        n='''    if (stableState == LOW) {
      Serial.println("BUTTON PRESSED");'''
        if n not in text:
            raise ValueError("Button callback layout differs; no changes applied")
        text=text.replace(n,'''    if (stableState == LOW) {
      buttonPressCount++;
      Serial.println("BUTTON PRESSED");''')
    elif 'Serial.println(button == LOW ? "BUTTON PRESSED" : "BUTTON RELEASED");' in text:
        n = 'Serial.println(button == LOW ? "BUTTON PRESSED" : "BUTTON RELEASED");'
        text=text.replace(n, 'if (button == LOW) buttonPressCount++;\n    '+n)
    else:
        setup='''  Serial.begin(115200);'''
        if setup not in text or 'server.handleClient();' not in text:
            raise ValueError("Firmware setup/loop layout differs; no changes applied")
        text=text.replace(setup,setup+'\n  pinMode(3, INPUT_PULLUP);  // physical voice button',1)
        callback='''
// Debounced press counter, safe to poll over local authenticated HTTP.
void checkPushButton() {
  static int rawPrevious = HIGH;
  static int stable = HIGH;
  static uint32_t changedAt = 0;
  int raw = digitalRead(3);
  uint32_t now = millis();
  if (raw != rawPrevious) { changedAt = now; rawPrevious = raw; }
  if (raw != stable && uint32_t(now - changedAt) >= 40) {
    stable = raw;
    if (stable == LOW) { buttonPressCount++; Serial.println("BUTTON PRESSED"); }
    else { Serial.println("BUTTON RELEASED"); }
  }
}

'''
        text=text.replace('void setup() {',callback+'void setup() {',1)
        # insert after client request handling; does not touch servo code
        text=text.replace('  server.handleClient();', '  server.handleClient();\n  checkPushButton();',1)
    needle='''  server.on("/steer", HTTP_GET, []() {'''
    if needle not in text:
        raise ValueError("Cannot find /steer endpoint; no changes applied")
    endpoint='''  // Read-only: no servo actuation and no Wi-Fi credentials exposed.
  server.on("/button", HTTP_GET, []() {
    server.sendHeader("Cache-Control", "no-store");
    if (!tokenValid()) {
      server.send(401, "application/json", "{\\"error\\":\\"unauthorized\\"}");
      return;
    }
    String body = String("{\\"press_count\\":") + String(buttonPressCount) +
      ",\\"pressed\\":" + (digitalRead(3) == LOW ? "true" : "false") + "}";
    server.send(200, "application/json", body);
  });
'''
    text=text.replace(needle,endpoint+needle,1)
    return text


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('sketch', type=Path)
    args=ap.parse_args()
    src=args.sketch
    old=src.read_text()
    new=patch(old)
    if new == old:
        print('Button event endpoint already present; no changes')
    else:
        backup=src.with_name(src.name+f'.backup-{int(time.time())}')
        shutil.copy2(src,backup)
        src.write_text(new)
        print(f'Updated {src}\nBackup: {backup}')
    print('Open the EXISTING sketch in Arduino IDE and Upload to ESP32-C3.')
    print('The 5V buzzer/relay is not modified.')

if __name__=='__main__':
    main()
