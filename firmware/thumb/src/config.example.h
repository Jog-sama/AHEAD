#pragma once
// Copy to config.h beside this file (git-ignored). No pin is chosen here: set one only after the board and the servo's
// supply are verified (docs/HARDWARE.md). Until then the board advertises and answers, and emits no PWM.
#ifndef SERVO_PIN  // a cane build names its own (firmware/cane/platformio.ini)
#define SERVO_PIN (-1)
#endif
#define PIN_VERIFIED false
// Leave false until the 5 V rail, the common ground, the connector polarity and the current capacity are verified.
#define POWER_VERIFIED false
