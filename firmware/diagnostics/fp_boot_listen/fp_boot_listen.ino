// Catch the R5xx power-on handshake byte (0x55).
//
// fp_sweep cannot see it: the sensor emits it within milliseconds of getting
// power, while the sweep is still in its 2500ms USB-settle delay. This sketch
// opens the UART as the very first thing it does, buffers everything that
// arrives into RAM, and only then brings up USB serial to report -- so the
// report survives even though the bytes arrived before the host was listening.
#include <Arduino.h>

static const int FP_RX_PIN = 5;   // QT Py header pin labeled "TX" -- proven receive pin, see 2026-08-12-qtpy-uart-fault.md
static const int FP_TX_PIN = 16;  // QT Py header pin labeled "RX" -- proven transmit pin
static const uint32_t UART_BAUD = 57600;
static const uint32_t CAPTURE_MS = 3000;

HardwareSerial Finger(1);

static uint8_t captured[512];
static uint32_t stamps[512];
static size_t capturedLen = 0;

void setup() {
  Finger.begin(UART_BAUD, SERIAL_8N1, FP_RX_PIN, FP_TX_PIN);

  uint32_t start = millis();
  while (millis() - start < CAPTURE_MS) {
    while (Finger.available() && capturedLen < sizeof(captured)) {
      stamps[capturedLen] = millis() - start;
      captured[capturedLen++] = (uint8_t)Finger.read();
    }
  }

  Serial.begin(115200);
  uint32_t waitStart = millis();
  while (!Serial && millis() - waitStart < 4000) delay(10);
  delay(300);

  Serial.println("=== boot listen ===");
  Serial.printf("baud=%lu rx_pin=%d captured=%u bytes in first %lums\n",
                (unsigned long)UART_BAUD, FP_RX_PIN,
                (unsigned)capturedLen, (unsigned long)CAPTURE_MS);

  if (capturedLen == 0) {
    Serial.println("SILENCE -- nothing arrived on RX during power-up");
  } else {
    Serial.print("bytes=");
    for (size_t i = 0; i < capturedLen; i++) Serial.printf("%02x", captured[i]);
    Serial.println();
    Serial.printf("first byte 0x%02x at t+%lums\n",
                  captured[0], (unsigned long)stamps[0]);
    if (captured[0] == 0x55) {
      Serial.println(">>> 0x55 HANDSHAKE SEEN -- sensor TX path is alive <<<");
    }
  }
  Serial.flush();
}

void loop() {
  while (Finger.available()) {
    Serial.printf("late byte %02x\n", (uint8_t)Finger.read());
    Serial.flush();
  }
  delay(50);
}
