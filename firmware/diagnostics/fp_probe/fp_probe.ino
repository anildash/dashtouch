// Raw protocol probe, using the exact hand-rolled packet path that fp_led
// proved works (clean 0xEF01 ACKs back from the module).
//
// Purpose: fp_sweep reports verifyPassword=fail on every combination while
// fp_led gets valid replies on the same pins/baud. That points at the
// Adafruit library's usage in the sweep rather than at the link, so this
// sketch removes the library from the picture and dumps raw bytes.
//
// Also sends ReadSysPara (0x0F), whose reply carries fingerprint capacity,
// security level and baud register -- the closest thing to a model ID we can
// get from an unbranded module.
#include <Arduino.h>

static const int FP_RX_PIN = 5;   // pad labeled "TX" -- proven receive pin
static const int FP_TX_PIN = 16;  // pad labeled "RX" -- proven transmit pin
static const uint32_t UART_BAUD = 57600;

HardwareSerial Finger(1);

void sendCmd(uint8_t instr, const uint8_t *params, size_t plen) {
  uint8_t payload[16];
  payload[0] = instr;
  if (plen) memcpy(payload + 1, params, plen);
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

void probe(const char *label, uint8_t instr, const uint8_t *params, size_t plen) {
  while (Finger.available()) Finger.read();   // drain
  sendCmd(instr, params, plen);

  uint8_t buf[64];
  size_t n = 0;
  uint32_t deadline = millis() + 700;
  while (millis() < deadline && n < sizeof(buf)) {
    if (Finger.available()) buf[n++] = (uint8_t)Finger.read();
  }

  Serial.printf("%-18s instr=0x%02x -> %u bytes: ", label, instr, (unsigned)n);
  for (size_t i = 0; i < n; i++) Serial.printf("%02x", buf[i]);
  if (n >= 10 && buf[0] == 0xef && buf[1] == 0x01) {
    Serial.printf("   [confirm=0x%02x]", buf[9]);
  }
  Serial.println();
  Serial.flush();
}

void setup() {
  Serial.begin(115200);
  delay(2500);
  Finger.begin(UART_BAUD, SERIAL_8N1, FP_RX_PIN, FP_TX_PIN);
  delay(300);
  Serial.println("=== raw protocol probe ===");
  Serial.flush();
}

void loop() {
  const uint8_t pw[4] = {0, 0, 0, 0};
  probe("VerifyPassword", 0x13, pw, sizeof(pw));   // what fp_sweep does
  probe("ReadSysPara",    0x0f, nullptr, 0);       // capacity / security / baud
  probe("AuraLed OFF",    0x35, (const uint8_t[]){4, 0x80, 7, 0}, 4);  // known-good control

  Serial.println("--- cycle done ---\n");
  Serial.flush();
  delay(3000);
}
