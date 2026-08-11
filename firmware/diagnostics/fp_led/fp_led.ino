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

static const int FP_RX_PIN = 16;
static const int FP_TX_PIN = 5;

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

void loop() {
  // Baseline: let whatever it does naturally be visible.
  Serial.println("\n--- sending NOTHING (baseline idle) ---");
  Serial.flush();
  hold("baseline: note the current ring behaviour", 6);

  // The critical test, via both command bytes, repeated hard.
  Serial.println("--- now spamming OFF via 0x35 ---");
  Serial.flush();
  for (int i = 0; i < 20; i++) { aura35(4, 7); delay(100); }
  hold("OFF via 0x35 -- did it go dark?", 6);

  Serial.println("--- now spamming OFF via 0x3c ---");
  Serial.flush();
  for (int i = 0; i < 20; i++) { aura3c(4, 7); delay(100); }
  hold("OFF via 0x3c -- did it go dark?", 6);

  // Unambiguous non-blue steady color: red. Default idle is never solid red.
  Serial.println("--- now spamming SOLID RED via 0x35 ---");
  Serial.flush();
  for (int i = 0; i < 20; i++) { aura35(3, 1); delay(100); }
  hold("SOLID RED via 0x35 -- did it turn red?", 6);

  Serial.println("--- now spamming SOLID RED via 0x3c ---");
  Serial.flush();
  for (int i = 0; i < 20; i++) { aura3c(3, 1); delay(100); }
  hold("SOLID RED via 0x3c -- did it turn red?", 6);

  Serial.println("\n=== cycle done, repeating ===");
  Serial.flush();
}
