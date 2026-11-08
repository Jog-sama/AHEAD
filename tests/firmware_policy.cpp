#include <cassert>
#include <climits>
#include <iostream>
#include "../firmware/TactileVector/Safety.h"
int main() {
  int n=90;
  const char* invalid[]={"", "-90", "+90", "90.0", " 90", "90 ", "90x", "nan", "59", "121", "999999999", "0", "180"};
  for (auto s: invalid) assert(!safety::parseAngle(s,n));
  assert(!safety::parseAngle(nullptr,n));
  assert(safety::parseAngle("60",n) && n==60);
  assert(safety::parseAngle("120",n) && n==120);
  for (int i=60;i<=120;i++) { assert(safety::pulseUs(i)>=1167); assert(safety::pulseUs(i)<=1833); }
  assert(safety::pulseUs(90)==1500);
  assert(safety::duty(90)==1229);
  assert(!safety::expired(1799,1000));
  assert(safety::expired(1800,1000));
  assert(safety::expired(700, UINT_MAX-100)); // millis rollover
  assert(!safety::expired(100, UINT_MAX-100));
  std::cout << "Firmware safety policy: parsing, bounds, PWM math, timeout/rollover PASS\n";
}
