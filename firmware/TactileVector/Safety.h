#pragma once
#include <stdint.h>
#include <stddef.h>

namespace safety {
constexpr int MIN_ANGLE = 60;
constexpr int NEUTRAL = 90;
constexpr int MAX_ANGLE = 120;
constexpr uint32_t TIMEOUT_MS = 800;
// 0..180 mapped to 500..2500 us, so a logical degree is near one horn degree on an SG90 clone (whose 500-2400 us spans
// about 180 degrees), then restricted to 60..120: 1167..1833 us, inside the 1000..2000 us that kept clear of the end
// stops. The old 1000..2000 mapping turned 80/100 into about +-5 degrees, 1.5-2 mm at the paddle, which the bench saw
// as barely moving; what a walker feels is unmeasured. Degrees per microsecond vary by clone; measure this servo first.
inline uint32_t pulseUs(int angle) { return 500U + (uint32_t(angle) * 2000U + 90U) / 180U; }
inline uint32_t duty(int angle) { return (pulseUs(angle) * 16384U + 10000U) / 20000U; }
inline bool parseAngle(const char* s, int& value) {
  if (!s || !*s) return false;
  int n = 0;
  size_t len = 0;
  while (*s) {
    if (++len > 3 || *s < '0' || *s > '9') return false;
    n = n * 10 + (*s++ - '0');
  }
  if (n < MIN_ANGLE || n > MAX_ANGLE) return false;
  value = n;
  return true;
}
inline bool expired(uint32_t now, uint32_t last) { return uint32_t(now-last) >= TIMEOUT_MS; }
}
