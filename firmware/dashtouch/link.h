#pragma once
#include <Arduino.h>

void linkBuildEv(uint16_t slot, uint16_t score, char* out, size_t outLen);
bool linkDecryptPw(const char* line, char* pwOut, size_t pwLen);
void linkHandleCommand(const String& line);
bool linkSelfTest();

// Set by the .ino; invoked for ENROLL/DELETE commands.
extern void (*linkOnEnroll)(uint16_t slot);
extern void (*linkOnDelete)(uint16_t slot);
