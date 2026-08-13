#include "r503.h"
#include "config.h"

bool R503::begin(HardwareSerial& port, int rxPin, int txPin, uint32_t baud) {
  ser_ = &port;
  ser_->begin(baud, SERIAL_8N1, rxPin, txPin);
  delay(120);
  while (ser_->available()) ser_->read();
  return true;
}

void R503::sendPacket(uint8_t instr, const uint8_t* params, size_t plen) {
  uint16_t length = plen + 3;  // instr + params + 2 checksum bytes
  uint32_t sum = 0x01 + (length >> 8) + (length & 0xff) + instr;
  for (size_t i = 0; i < plen; i++) sum += params[i];
  uint8_t header[] = {0xef, 0x01, 0xff, 0xff, 0xff, 0xff, 0x01,
                      (uint8_t)(length >> 8), (uint8_t)(length & 0xff), instr};
  ser_->write(header, sizeof(header));
  if (plen) ser_->write(params, plen);
  ser_->write((uint8_t)(sum >> 8));
  ser_->write((uint8_t)(sum & 0xff));
  ser_->flush();
}

int R503::readAck(uint8_t* data, size_t maxLen, size_t* gotLen,
                  uint32_t timeoutMs) {
  uint8_t buf[64];
  size_t n = 0;
  uint32_t deadline = millis() + timeoutMs;
  // Need at least: header(2)+addr(4)+type(1)+len(2)+confirm(1)+cksum(2)=12
  while (millis() < deadline && n < sizeof(buf)) {
    if (!ser_->available()) continue;
    buf[n++] = (uint8_t)ser_->read();
    if (n >= 9) {
      uint16_t plen = ((uint16_t)buf[7] << 8) | buf[8];
      if (n >= (size_t)(9 + plen)) break;  // full packet in hand
    }
  }
  if (n < 12 || buf[0] != 0xef || buf[1] != 0x01 || buf[6] != 0x07)
    return R503_TIMEOUT;
  uint16_t plen = ((uint16_t)buf[7] << 8) | buf[8];

  // Validate packet checksum; reject corrupted packets
  uint32_t cksum = buf[6] + buf[7] + buf[8];
  for (size_t i = 0; i < plen - 2; i++) {
    cksum += buf[9 + i];
  }
  uint16_t rxCksum = ((uint16_t)buf[9 + plen - 2] << 8) | buf[9 + plen - 1];
  if ((uint16_t)(cksum & 0xffff) != rxCksum)
    return R503_TIMEOUT;

  uint8_t confirm = buf[9];
  size_t dataBytes = (plen >= 3) ? plen - 3 : 0;  // minus confirm + cksum
  if (data && gotLen) {
    size_t copyN = dataBytes < maxLen ? dataBytes : maxLen;
    memcpy(data, buf + 10, copyN);
    *gotLen = copyN;
  }
  return confirm;
}

int R503::command(uint8_t instr, const uint8_t* params, size_t plen,
                  uint8_t* data, size_t maxLen, size_t* gotLen,
                  uint32_t timeoutMs) {
  while (ser_->available()) ser_->read();  // drain strays
  sendPacket(instr, params, plen);
  return readAck(data, maxLen, gotLen, timeoutMs);
}

int R503::verifyPassword() {
  const uint8_t p[4] = {0, 0, 0, 0};
  return command(0x13, p, sizeof(p));
}

int R503::readSysPara(uint16_t* capacity, uint16_t* secLevel) {
  uint8_t d[16];
  size_t got = 0;
  int c = command(0x0f, nullptr, 0, d, sizeof(d), &got);
  if (c == 0 && got >= 8) {
    if (capacity) *capacity = ((uint16_t)d[4] << 8) | d[5];
    if (secLevel) *secLevel = ((uint16_t)d[6] << 8) | d[7];
  }
  return c;
}

int R503::genImg() { return command(0x01, nullptr, 0); }

int R503::img2Tz(uint8_t buf) { return command(0x02, &buf, 1, nullptr, 0, nullptr, 2000); }

int R503::regModel() { return command(0x05, nullptr, 0, nullptr, 0, nullptr, 2000); }

int R503::storeTemplate(uint16_t slot) {
  const uint8_t p[3] = {0x01, (uint8_t)(slot >> 8), (uint8_t)(slot & 0xff)};
  return command(0x06, p, sizeof(p), nullptr, 0, nullptr, 2000);
}

int R503::deleteTemplate(uint16_t slot) {
  const uint8_t p[4] = {(uint8_t)(slot >> 8), (uint8_t)(slot & 0xff), 0x00, 0x01};
  return command(0x0c, p, sizeof(p), nullptr, 0, nullptr, 2000);
}

int R503::search(uint16_t* slot, uint16_t* score) {
  // CharBuffer 1, whole library.
  const uint8_t p[5] = {0x01, 0x00, 0x00,
                        (uint8_t)(DT_MAX_SLOT >> 8), (uint8_t)(DT_MAX_SLOT & 0xff)};
  uint8_t d[4];
  size_t got = 0;
  int c = command(0x04, p, sizeof(p), d, sizeof(d), &got, 2000);
  if (c == 0 && got >= 4) {
    if (slot) *slot = ((uint16_t)d[0] << 8) | d[1];
    if (score) *score = ((uint16_t)d[2] << 8) | d[3];
  }
  return c;
}

int R503::auraCtl(uint8_t mode, uint8_t speed, uint8_t color, uint8_t count) {
  const uint8_t p[4] = {mode, speed, color, count};
  return command(0x35, p, sizeof(p));
}
