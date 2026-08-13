// Decisive LED test: is the ring OBEYING us, or just sitting in its factory
// default "breathing blue" idle animation and ignoring everything?
//
// Strategy: hold a single unambiguous state for a long dwell, so there's no
// confusion about what should be on screen. OFF is the key state -- the sensor
// will never spontaneously turn its own ring off, so if it goes dark, it is
// definitely receiving and executing our commands.
//
// Tries BOTH known Aura command bytes:
//   0x35 = AuraLedConfig, per the R503/R5xx spec and R503Lib
//   0x3c = what the original tinyTouch firmware used for its ZW101/ZW111
#include <Arduino.h>

static const int FP_RX_PIN = 5;   // QT Py header pin labeled "TX" -- proven receive pin, see 2026-08-12-qtpy-uart-fault.md
static const int FP_TX_PIN = 16;  // QT Py header pin labeled "RX" -- proven transmit pin

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

  // We know this exact command reaches and is executed by the sensor (the
  // ring visibly obeys it). Listen briefly for any reply, to separate
  // "sensor never replies to anything" from "the Adafruit library's
  // VerifyPassword specifically gets no reply."
  delay(150);
  int n = Finger.available();
  if (n > 0) {
    Serial.printf("  <-- reply to instr=0x%02x: %d bytes: ", instr, n);
    while (Finger.available()) Serial.printf("%02x", (uint8_t)Finger.read());
    Serial.println();
    Serial.flush();
  }
}

// control: 1=breathe 2=flash 3=on 4=off ; color: 1=red 2=blue 3=purple 4=green 7=white
void aura35(uint8_t control, uint8_t color) {
  uint8_t p[4] = {control, 0x80, color, 0};
  sendCmd(0x35, p, sizeof(p));
}
// legacy/ZW-style ordering used by the original tinyTouch firmware
void aura3c(uint8_t control, uint8_t color) {
  uint8_t p[4] = {control, color, color, 0};
  sendCmd(0x3c, p, sizeof(p));
}

void hold(const char *label, int seconds) {
  Serial.printf("\n>>> %s  (hold %ds)\n", label, seconds);
  Serial.flush();
  delay((uint32_t)seconds * 1000);
}

void setup() {
  Serial.begin(115200);
  delay(2500);
  Finger.begin(57600, SERIAL_8N1, FP_RX_PIN, FP_TX_PIN);
  delay(500);
  Serial.println("=== decisive LED test ===");
  Serial.println("KEY QUESTION: does the ring EVER go fully dark?");
  Serial.println("The sensor will not turn its own ring off on its own.");
  Serial.flush();
}

// Which command byte does this module actually speak?
//   0x35 = AuraLedConfig, the R503/R50x command
//   0x3c = the legacy byte tinyTouch's firmware used for ZW101/ZW111
//
// Each phase drives the ring to an unambiguous state and holds it. The two
// phases are kept strictly separate: if 0x35's OFF works, sending 0x3c's OFF
// to an already-dark ring proves nothing, so each phase starts by driving a
// LIT state before testing OFF.
void loop() {
  Serial.println("\n--- sending NOTHING (baseline idle) ---");
  Serial.flush();
  hold("baseline: note the ring's natural behaviour", 5);

  Serial.println("\n=== PHASE 1: ONLY 0x35 (R503 AuraLedConfig) ===");
  Serial.flush();
  for (int i = 0; i < 6; i++) { aura35(3, 1); delay(80); }
  hold("[0x35] SOLID RED?", 5);
  for (int i = 0; i < 6; i++) { aura35(4, 7); delay(80); }
  hold("[0x35] OFF / fully dark?", 5);

  Serial.println("\n=== PHASE 2: ONLY 0x3c (ZW101/ZW111 legacy) ===");
  Serial.flush();
  for (int i = 0; i < 6; i++) { aura3c(3, 1); delay(80); }
  hold("[0x3c] SOLID RED?", 5);
  for (int i = 0; i < 6; i++) { aura3c(4, 7); delay(80); }
  hold("[0x3c] OFF / fully dark?", 5);

  Serial.println("\n=== cycle done, repeating ===");
  Serial.flush();
}
