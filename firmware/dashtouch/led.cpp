#include "led.h"
#include "settings.h"

// Aura constants: modes 1=breathe 2=flash 3=on 4=off; colors 1=red 2=blue
// 3=purple 4=green 5=yellow 6=cyan 7=white. Full palette verified on this
// project's unit with firmware/diagnostics/fp_colors.
//
// Idle rendering honors the user's stored idle_color/idle_style (Task
// 7m): color 0 sends aura OFF; otherwise style 1 (steady) sends mode 3,
// style 2 (breathing) sends mode 1 at DT_IDLE_BREATHE_SPEED. Five of the
// seven colors already double as status signals elsewhere in this file
// (1 red = device problem, 4 green = matched, 5 yellow = Mac unreachable,
// 6 cyan = lift, 7 white = reading) — only 3 purple and 2 blue are
// unclaimed. The firmware permits any choice here; the web page is the
// one that warns about the collision.
static R503* s_sensor = nullptr;
static DtLedState s_current = (DtLedState)-1;

// Speed for breathing idle: the R503's speed byte runs roughly 0 (fast)
// to 255 (slow-ish); 100 read as a calm, several-second fade rather than
// a pulse when tried by eye on hardware — tune here if a unit disagrees.
static const uint8_t DT_IDLE_BREATHE_SPEED = 100;

static void renderIdle() {
  if (!s_sensor) return;
  uint8_t color = settingsIdleColor();
  if (color == 0) {
    s_sensor->auraCtl(4, 0, 0, 0);  // dark is dark — mode/speed/count don't matter
    return;
  }
  if (settingsIdleStyle() == 2) {
    s_sensor->auraCtl(1, DT_IDLE_BREATHE_SPEED, color, 0);  // breathing
  } else {
    s_sensor->auraCtl(3, 0, color, 0);  // steady
  }
}

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
    case DT_LED_IDLE:         renderIdle();                    break;
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

void ledApplyIdleNow() {
  if (s_current != DT_LED_IDLE) return;  // a SET while mid-touch waits its turn
  renderIdle();
}
