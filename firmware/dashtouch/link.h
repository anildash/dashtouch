#pragma once
#include <Arduino.h>

void linkBuildEv(uint16_t slot, uint16_t score, char* out, size_t outLen);
bool linkDecryptPw(const char* line, char* pwOut, size_t pwLen);
void linkHandleCommand(const String& line);
bool linkSelfTest();

// True while the host has paused matching (e.g. a naming/renaming field is
// focused in the web UI). Also enforces the 90s auto-resume: call this from
// loop() every tick, not just when STATUS is requested, so a dead helper
// can't leave the sensor deaf forever. See docs/protocol.md.
bool linkIsPaused();

// Set by the .ino; invoked for ENROLL/DELETE commands.
extern void (*linkOnEnroll)(uint16_t slot);
extern void (*linkOnDelete)(uint16_t slot);
// Set by the .ino; invoked after SET fp_swap persists the new value. Does
// NOT attempt a live UART re-init (real hardware testing showed that's
// unreliable and can misreport) — it marks the sensor state unverified.
// A reboot is required before the new orientation's health can be trusted;
// the SET_OK reply says so explicitly (reboot_required).
extern void (*linkOnFpSwapChanged)();
