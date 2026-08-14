#pragma once
#include <Arduino.h>

void linkBuildEv(uint16_t slot, uint16_t score, char* out, size_t outLen);
bool linkDecryptPw(const char* line, char* pwOut, size_t pwLen);
void linkHandleCommand(const String& line);
bool linkSelfTest();

// True while the host has paused matching (e.g. a naming/renaming field is
// focused in the web UI). A read-only query — it does NOT itself enforce
// the auto-resume timeout (linkTickPause() owns that), so calling this
// from STATUS or the loop's scan gate can never race the tick below.
bool linkIsPaused();

// Auto-resume tick. Call this from loop() unconditionally, every single
// iteration, before any other gate (g_sensorOk, the poll throttle, the
// pause branch itself) — nothing may skip it, or a paused device could get
// stuck past its 90s deadline with no way back. When the deadline passes
// with no PAUSE 1 refresh, this clears the pause AND announces it
// unsolicited on the serial link (`PAUSE_OK 0`), so the helper learns
// about the resume without having to ask. See docs/protocol.md.
void linkTickPause();

// Set by the .ino; invoked for ENROLL/DELETE commands.
extern void (*linkOnEnroll)(uint16_t slot);
extern void (*linkOnDelete)(uint16_t slot);
// Set by the .ino; invoked after SET fp_swap persists the new value. Does
// NOT attempt a live UART re-init (real hardware testing showed that's
// unreliable and can misreport) — it marks the sensor state unverified.
// A reboot is required before the new orientation's health can be trusted;
// the SET_OK reply says so explicitly (reboot_required).
extern void (*linkOnFpSwapChanged)();
