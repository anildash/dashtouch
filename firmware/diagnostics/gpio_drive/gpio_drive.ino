// Plain GPIO drive test -- no UART involved.
//
// Keep the same single jumper between the pad labeled TX (GPIO 5) and the pad
// labeled RX (GPIO 16). This drives each pin as a bare digital output and
// reads the other as a digital input, which separates two very different
// faults:
//
//   GPIO 5 drives fine here  -> the pin is healthy and the UART peripheral
//                               simply will not route TX onto it. Fix is a
//                               constant change, not a new board.
//   GPIO 5 cannot drive high -> the output driver is genuinely damaged. Remap
//                               TX to a different free pin, or replace the board.
#include <Arduino.h>

static const int PIN_TX = 5;
static const int PIN_RX = 16;

int probe(int outPin, int inPin, int level) {
  pinMode(outPin, OUTPUT);
  pinMode(inPin, INPUT);
  digitalWrite(outPin, level);
  delay(50);
  return digitalRead(inPin);
}

void report(int outPin, int inPin) {
  int high = probe(outPin, inPin, HIGH);
  int low = probe(outPin, inPin, LOW);
  bool ok = (high == 1 && low == 0);
  Serial.printf("drive GPIO %-2d -> read GPIO %-2d : high=%d low=%d  %s\n",
                outPin, inPin, high, low,
                ok ? "OK" : (high == 0 ? "STUCK LOW -- cannot drive high" : "INCONSISTENT"));
  Serial.flush();
}

void setup() {
  Serial.begin(115200);
  delay(2500);
}

void loop() {
  Serial.println("=== gpio drive test start ===");
  report(PIN_TX, PIN_RX);
  report(PIN_RX, PIN_TX);
  Serial.println("=== gpio drive test complete ===");
  Serial.flush();
  delay(3000);
}
