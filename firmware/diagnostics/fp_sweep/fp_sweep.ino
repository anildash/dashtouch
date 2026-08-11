// Diagnostic sweep: try the official Adafruit_Fingerprint library against the
// sensor at every plausible baud rate, in BOTH TX/RX orientations.
// Requires no finger on the sensor -- verifyPassword() is a pure handshake.
#include <Arduino.h>
#include <Adafruit_Fingerprint.h>

static const int PIN_A = 16;  // QT Py header pin labeled "RX"
static const int PIN_B = 5;   // QT Py header pin labeled "TX"

HardwareSerial fserial(1);
Adafruit_Fingerprint finger(&fserial);

const uint32_t BAUDS[] = {57600, 9600, 19200, 38400, 115200, 28800, 76800};
const int NBAUDS = sizeof(BAUDS) / sizeof(BAUDS[0]);

void tryCombo(uint32_t baud, int rxPin, int txPin, const char *label) {
  fserial.end();
  delay(60);
  fserial.begin(baud, SERIAL_8N1, rxPin, txPin);
  delay(350);

  // Drain anything stale.
  while (fserial.available()) fserial.read();

  bool ok = finger.verifyPassword();

  // Regardless of the library result, report how many raw bytes came back,
  // so "silence" and "garbage" are distinguishable.
  delay(120);
  int extra = fserial.available();
  Serial.printf("baud=%-7lu %s verifyPassword=%s trailing_bytes=%d",
                (unsigned long)baud, label, ok ? "OK" : "fail", extra);
  if (extra > 0) {
    Serial.print(" raw=");
    for (int i = 0; i < extra && i < 24; i++) Serial.printf("%02x", fserial.read());
  }
  Serial.println();
  Serial.flush();

  if (ok) {
    Serial.println(">>> HANDSHAKE SUCCEEDED <<<");
    finger.getParameters();
    Serial.printf("    status=0x%x capacity=%u security=%u baud_reg=%u\n",
                  finger.status_reg, finger.capacity,
                  finger.security_level, finger.baud_rate);
    Serial.flush();
  }
}

void setup() {
  Serial.begin(115200);
  delay(2500);
}

void runSweep() {
  Serial.println("=== fingerprint sweep start ===");
  Serial.flush();

  for (int pass = 0; pass < 2; pass++) {
    for (int i = 0; i < NBAUDS; i++) {
      if (pass == 0) {
        tryCombo(BAUDS[i], PIN_A, PIN_B, "rx=16(RX) tx=5(TX) [as-wired] ");
      } else {
        tryCombo(BAUDS[i], PIN_B, PIN_A, "rx=5(TX)  tx=16(RX) [swapped] ");
      }
    }
  }

  Serial.println("=== sweep complete ===");
  Serial.flush();
}

void loop() {
  runSweep();
  delay(3000);
}
