#pragma once
#include "r503.h"

// The official LED language (spec §5). Red = device-side problem only;
// yellow = Mac-side problem only; cyan = enroll-lift only.
enum DtLedState {
  DT_LED_IDLE,          // steady purple
  DT_LED_READING,       // steady white
  DT_LED_MATCH,         // green flash x2
  DT_LED_NOMATCH,       // red flash x2
  DT_LED_HELPER_WAIT,   // steady yellow
  DT_LED_ENROLL_PLACE,  // breathing white
  DT_LED_ENROLL_LIFT,   // steady cyan
  DT_LED_ENROLL_OK,     // green flash x3
  DT_LED_ENROLL_FAIL,   // red flash x3
  DT_LED_BOOT_FAIL      // best-effort steady red (ring may be unreachable)
};

void ledInit(R503* sensor);
void ledSet(DtLedState s);
void boardLedRed(bool on);
