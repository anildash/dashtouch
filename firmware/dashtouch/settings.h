#pragma once
#include <Arduino.h>

// Device settings, persisted in NVS (ESP32 Preferences, namespace
// "dashtouch") so they're correct from power-on rather than depending on
// the helper to push them down every session. See docs/protocol.md for
// the SETTINGS / SET wire commands that read and write these.
void settingsInit();

// idle_color: the R503's own color numbering, which is literally a 3-bit
// RGB mask (bit0 red, bit1 blue, bit2 green) — hence exactly seven colors
// and no in-between hues or brightness. 0 = off (dark), 1 red, 2 blue,
// 3 purple, 4 green, 5 yellow, 6 cyan, 7 white.
uint8_t settingsIdleColor();
// idle_style: 1 = steady, 2 = breathing. Meaningless (and ignored) when
// idle_color is 0 — dark is dark either way.
uint8_t settingsIdleStyle();
bool settingsPressEnter();

// Setters validate and persist; return false (and leave the stored value
// unchanged) on an out-of-range input.
bool settingsSetIdleColor(uint8_t v);
bool settingsSetIdleStyle(uint8_t v);
void settingsSetPressEnter(bool v);
