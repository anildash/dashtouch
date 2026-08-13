#pragma once
#include <Arduino.h>

#define R503_TIMEOUT -1

class R503 {
 public:
  bool begin(HardwareSerial& port, int rxPin, int txPin, uint32_t baud);
  int verifyPassword();
  int readSysPara(uint16_t* capacity, uint16_t* secLevel);
  int genImg();
  int img2Tz(uint8_t buf);
  int regModel();
  int storeTemplate(uint16_t slot);
  int deleteTemplate(uint16_t slot);
  int search(uint16_t* slot, uint16_t* score);
  int auraCtl(uint8_t mode, uint8_t speed, uint8_t color, uint8_t count);
  // Reads one 32-byte slot-usage bitmap page (bit i of byte b = slot
  // b*8+i used, LSB-first). Page 0 covers slots 0-255. Copies exactly 32
  // payload bytes to out on confirm 0.
  int readIndexTable(uint8_t page, uint8_t out[32]);

 private:
  HardwareSerial* ser_ = nullptr;
  void sendPacket(uint8_t instr, const uint8_t* params, size_t plen);
  // Reads one ack packet; returns confirm code or R503_TIMEOUT. Payload
  // bytes after the confirm code are copied to data (up to maxLen).
  int readAck(uint8_t* data, size_t maxLen, size_t* gotLen, uint32_t timeoutMs);
  int command(uint8_t instr, const uint8_t* params, size_t plen,
              uint8_t* data = nullptr, size_t maxLen = 0,
              size_t* gotLen = nullptr, uint32_t timeoutMs = 1000);
};
