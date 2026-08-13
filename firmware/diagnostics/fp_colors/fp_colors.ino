// Ring palette survey: what does THIS unit's aura ring actually support?
//
// R503-class clones vary -- many listings advertise only a "2-color ring,"
// and colors the spec defines (yellow, cyan...) may render wrong, identical
// to each other, or not at all. Run this once on any new unit and note what
// you actually see; define the firmware's LED language only from colors that
// render distinctly.
//
// The sequence is fixed and self-describing so no serial monitor is needed:
//
//   COLOR PHASE -- 3s each, 1s dark between:
//     1 red, 2 blue, 3 purple, 4 green, 5 yellow, 6 cyan, 7 white
//   MODE PHASE -- on blue, 4s each, 1s dark between:
//     breathing, flashing, fade-in (then hold), fade-out
//   then 5s dark, and the whole cycle repeats.
//
// Serial mirrors the schedule for a host-side capture, but eyes are the
// instrument here.
#include <Arduino.h>

static const int FP_RX_PIN = 5;   // pad labeled "TX" -- this build's board, see
static const int FP_TX_PIN = 16;  // docs/superpowers/references/2026-08-12-qtpy-uart-fault.md

HardwareSerial Finger(1);

void sendCmd(uint8_t instr, const uint8_t *params, size_t plen) {
  uint8_t payload[8];
  payload[0] = instr;
  memcpy(payload + 1, params, plen);
  size_t payloadLen = plen + 1;
  uint16_t length = payloadLen + 2;
  uint32_t sum = 0x01 + (length >> 8) + (length & 0xff);
  for (size_t i = 0; i < payloadLen; i++) sum += payload[i];

  uint8_t header[] = {0xef, 0x01, 0xff, 0xff, 0xff, 0xff, 0x01,
                      (uint8_t)(length >> 8), (uint8_t)(length & 0xff)};
  Finger.write(header, sizeof(header));
  Finger.write(payload, payloadLen);
  Finger.write((uint8_t)(sum >> 8));
  Finger.write((uint8_t)(sum & 0xff));
  Finger.flush();
  delay(120);
  while (Finger.available()) Finger.read();  // drain the ACK
}

// control: 1=breathe 2=flash 3=on 4=off 5=fade-in 6=fade-out
// speed: cycle time for animated modes; count: 0=forever
void aura(uint8_t control, uint8_t speed, uint8_t color, uint8_t count) {
  uint8_t p[4] = {control, speed, color, count};
  sendCmd(0x35, p, sizeof(p));
}

void dark(uint32_t ms) {
  aura(4, 0, 1, 0);
  delay(ms);
}

static const char *COLOR_NAMES[] = {
  "", "RED", "BLUE", "PURPLE", "GREEN", "YELLOW", "CYAN", "WHITE"
};

void setup() {
  Serial.begin(115200);
  delay(2500);
  Finger.begin(57600, SERIAL_8N1, FP_RX_PIN, FP_TX_PIN);
  delay(300);
  Serial.println("=== ring palette survey ===");
  Serial.flush();
}

void loop() {
  Serial.println("--- color phase: 3s each, 1s dark between ---");
  Serial.flush();
  for (uint8_t c = 1; c <= 7; c++) {
    Serial.printf("color %u: %s\n", c, COLOR_NAMES[c]);
    Serial.flush();
    aura(3, 0, c, 0);       // steady on
    delay(3000);
    dark(1000);
  }

  Serial.println("--- mode phase: on BLUE, 4s each ---");
  Serial.flush();

  Serial.println("mode: BREATHING");
  Serial.flush();
  aura(1, 100, 2, 0);
  delay(4000);
  dark(1000);

  Serial.println("mode: FLASHING");
  Serial.flush();
  aura(2, 25, 2, 0);
  delay(4000);
  dark(1000);

  Serial.println("mode: FADE-IN then hold");
  Serial.flush();
  aura(5, 100, 2, 0);
  delay(4000);
  dark(1000);

  Serial.println("mode: FADE-OUT (starts lit, dims)");
  Serial.flush();
  aura(3, 0, 2, 0);         // light it first so the fade is visible
  delay(600);
  aura(6, 100, 2, 0);
  delay(3400);

  Serial.println("=== cycle done, 5s dark, repeating ===");
  Serial.flush();
  dark(5000);
}
