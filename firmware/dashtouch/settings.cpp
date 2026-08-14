#include "settings.h"
#include "config.h"
#include <Preferences.h>

static Preferences s_prefs;
static uint8_t s_idleColor = 3;   // 3 = purple, until settingsInit() loads NVS
static uint8_t s_idleStyle = 1;   // 1 = steady
static bool s_pressEnter = DT_PRESS_ENTER;

void settingsInit() {
  s_prefs.begin("dashtouch", false);
  s_idleColor = s_prefs.getUChar("idle_color", 3);
  if (s_idleColor > 7) s_idleColor = 3;  // guard against a corrupted NVS entry
  s_idleStyle = s_prefs.getUChar("idle_style", 1);
  if (s_idleStyle < 1 || s_idleStyle > 2) s_idleStyle = 1;
  // config.h's DT_PRESS_ENTER is the factory default only — once a value
  // has been stored (by a SET command), the stored value wins.
  s_pressEnter = s_prefs.getBool("press_enter", DT_PRESS_ENTER);
}

uint8_t settingsIdleColor() { return s_idleColor; }
uint8_t settingsIdleStyle() { return s_idleStyle; }
bool settingsPressEnter() { return s_pressEnter; }

bool settingsSetIdleColor(uint8_t v) {
  if (v > 7) return false;
  s_idleColor = v;
  s_prefs.putUChar("idle_color", v);
  return true;
}

bool settingsSetIdleStyle(uint8_t v) {
  if (v < 1 || v > 2) return false;
  s_idleStyle = v;
  s_prefs.putUChar("idle_style", v);
  return true;
}

void settingsSetPressEnter(bool v) {
  s_pressEnter = v;
  s_prefs.putBool("press_enter", v);
}
