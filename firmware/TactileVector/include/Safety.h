#pragma once
#include <stdint.h>
#include <stddef.h>

namespace safety {
constexpr int MIN_ANGLE = 75;
constexpr int NEUTRAL = 90;
constexpr int MAX_ANGLE = 105;
constexpr uint32_t TIMEOUT_MS = 800;
// Nominal 0..180 mapped conservatively to 1000..2000 us, then restricted to 75..105.
// Real clone servo geometry is not inferred from this mapping.
inline uint32_t pulseUs(int angle) { return 1000U + (uint32_t(angle) * 1000U + 90U) / 180U; }
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
