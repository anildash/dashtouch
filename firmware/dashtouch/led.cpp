#include "led.h"

// Aura constants: modes 1=breathe 2=flash 3=on 4=off; colors 1=red 2=blue
// 3=purple 4=green 5=yellow 6=cyan 7=white. Full palette verified on this
// project's unit with firmware/diagnostics/fp_colors.
static R503* s_sensor = nullptr;
static DtLedState s_current = (DtLedState)-1;

void ledInit(R503* sensor) {
  s_sensor = sensor;
  s_current = (DtLedState)-1;
#ifdef PIN_NEOPIXEL
#ifdef NEOPIXEL_POWER
  pinMode(NEOPIXEL_POWER, OUTPUT);
  digitalWrite(NEOPIXEL_POWER, HIGH);
#endif
  neopixelWrite(PIN_NEOPIXEL, 0, 0, 0);
#endif
}

void boardLedRed(bool on) {
#ifdef PIN_NEOPIXEL
  neopixelWrite(PIN_NEOPIXEL, on ? 32 : 0, 0, 0);
#endif
}

void ledSet(DtLedState s) {
  if (!s_sensor || s == s_current) return;  // transitions only, never spam
  s_current = s;
  switch (s) {
    case DT_LED_IDLE:         s_sensor->auraCtl(3, 0, 3, 0);   break;
    case DT_LED_READING:      s_sensor->auraCtl(3, 0, 7, 0);   break;
    case DT_LED_MATCH:        s_sensor->auraCtl(2, 25, 4, 2);  break;
    case DT_LED_NOMATCH:      s_sensor->auraCtl(2, 25, 1, 2);  break;
    case DT_LED_HELPER_WAIT:  s_sensor->auraCtl(3, 0, 5, 0);   break;
    case DT_LED_ENROLL_PLACE: s_sensor->auraCtl(1, 100, 7, 0); break;
    case DT_LED_ENROLL_LIFT:  s_sensor->auraCtl(3, 0, 6, 0);   break;
    case DT_LED_ENROLL_OK:    s_sensor->auraCtl(2, 25, 4, 3);  break;
    case DT_LED_ENROLL_FAIL:  s_sensor->auraCtl(2, 25, 1, 3);  break;
    case DT_LED_BOOT_FAIL:    s_sensor->auraCtl(3, 0, 1, 0);   break;
  }
}
